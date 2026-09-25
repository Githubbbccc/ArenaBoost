// ArenaBoost - Created by Ghost - Copyright (c) 2026 Ghost - MIT License
package com.arena.arenaboost

import android.app.ActivityManager
import android.app.GameManager
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.PixelFormat
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Gravity
import android.os.PowerManager
import android.provider.Settings
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.io.File

class MainActivity : FlutterActivity() {
    private val channel = "arenaboost/native"
    private var savedDndFilter: Int? = null
    private var savedAutoRotate: Int? = null
    private var savedUserRotation: Int? = null
    private val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var gameBarView: LinearLayout? = null
    private var gameBarText: TextView? = null
    private var lastCpuIdle = 0L
    private var lastCpuTotal = 0L

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channel).setMethodCallHandler { call, result ->
            try {
                when (call.method) {
                    "getApps" -> Thread {
                        val apps = getApps()
                        runOnUiThread { result.success(apps) }
                    }.start()
                    "launch" -> result.success(launch(call.argument<String>("pkg")!!))
                    "memInfo" -> result.success(memInfo())
                    "boost" -> {
                        // off the main thread: it scans all apps + sleeps ~700 ms,
                        // which would freeze the Flutter UI mid-"Boosting…"
                        val keep = call.argument<List<String>>("keep") ?: emptyList()
                        Thread {
                            val r = boost(keep)
                            runOnUiThread { result.success(r) }
                        }.start()
                    }
                    "deviceInfo" -> result.success(deviceInfo())
                    "hasDndAccess" -> result.success(nm().isNotificationPolicyAccessGranted)
                    "requestDndAccess" -> {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS)); result.success(true)
                    }
                    "setDnd" -> result.success(setDnd(call.argument<Boolean>("on") == true))
                    "canWriteSettings" -> result.success(Settings.System.canWrite(this))
                    "requestWriteSettings" -> {
                        startActivity(Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:$packageName")))
                        result.success(true)
                    }
                    "lockRotation" -> result.success(lockRotation(call.argument<String>("mode") ?: "off"))
                    "canDrawOverlays" -> result.success(canDrawOverlays())
                    "requestDrawOverlays" -> {
                        startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:$packageName")))
                        result.success(true)
                    }
                    "setGameBar" -> result.success(if (call.argument<Boolean>("on") == true)
                        gameBarOn(call.argument<String>("title") ?: "Boosted")
                    else gameBarOff())
                    "gameBarUpdate" -> result.success(gameBarSetText(call.argument<String>("text") ?: ""))
                    "gameMode" -> result.success(gameMode(call.argument<String>("pkg")!!))
                    "openAppSettings" -> {
                        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            Uri.parse("package:" + call.argument<String>("pkg"))))
                        result.success(true)
                    }
                    "openBatteryOpt" -> {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)); result.success(true)
                    }
                    "openDevOptions" -> {
                        startActivity(Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)); result.success(true)
                    }
                    else -> result.notImplemented()
                }
            } catch (e: Exception) {
                result.error("ERR", e.message, null)
            }
        }
    }

    private fun am() = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
    private fun nm() = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    // ---------- installed launchable apps, games flagged by Android category
    private fun getApps(): List<Map<String, Any>> {
        val pm = packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val list = pm.queryIntentActivities(intent, 0)
        val knownGames = listOf("pubg", "tencent.ig", "freefire", "dts.freefire", "garena", "codm",
            "activision", "mobile.legends", "moonton", "supercell", "roblox", "mojang", "minecraft",
            "miHoYo", "hoyoverse", "genshin", "riotgames", "wildrift", "ea.gp", "gameloft", "krafton",
            "bgmi", "asphalt", "clash", "brawl", "8ballpool", "miniclip", "ludo", "sniper", "fortnite")
        return list.distinctBy { it.activityInfo.packageName }
            .filter { it.activityInfo.packageName != packageName }
            .map { ri ->
                val ai = ri.activityInfo.applicationInfo
                val pkg = ai.packageName
                @Suppress("DEPRECATION")
                val flaggedGame = (Build.VERSION.SDK_INT >= 26 && ai.category == ApplicationInfo.CATEGORY_GAME) ||
                        (ai.flags and ApplicationInfo.FLAG_IS_GAME) != 0
                val nameGuess = knownGames.any { pkg.lowercase().contains(it.lowercase()) }
                mapOf(
                    "pkg" to pkg,
                    "name" to ri.loadLabel(pm).toString(),
                    "isGame" to (flaggedGame || nameGuess),
                    "icon" to iconBytes(ri.loadIcon(pm))
                )
            }.sortedBy { it["name"] as String }
    }

    private fun iconBytes(d: Drawable): ByteArray {
        val bmp = if (d is BitmapDrawable && d.bitmap != null) Bitmap.createScaledBitmap(d.bitmap, 96, 96, true)
        else {
            val b = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
            val c = Canvas(b); d.setBounds(0, 0, 96, 96); d.draw(c); b
        }
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.PNG, 90, out)
        return out.toByteArray()
    }

    private fun launch(pkg: String): Boolean {
        val i = packageManager.getLaunchIntentForPackage(pkg) ?: return false
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(i)
        return true
    }

    // ---------- memory
    private fun memInfo(): Map<String, Any> {
        val mi = ActivityManager.MemoryInfo()
        am().getMemoryInfo(mi)
        return mapOf("total" to mi.totalMem, "avail" to mi.availMem, "low" to mi.lowMemory,
            "threshold" to mi.threshold)
    }

    /**
     * Safe boost (no root): asks Android to kill *background/cached* processes of
     * all other user apps. Android only allows this for apps not in foreground and
     * it never touches system apps or the game. This is the maximum allowed without root.
     */
    private fun boost(keep: List<String>): Map<String, Any> {
        val before = memInfo()["avail"] as Long
        val pm = packageManager
        var count = 0
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val pkgs = pm.queryIntentActivities(intent, 0).map { it.activityInfo.applicationInfo }
            .filter { (it.flags and ApplicationInfo.FLAG_SYSTEM) == 0 }
            .map { it.packageName }.toSet()
        for (p in pkgs) {
            if (p == packageName || keep.contains(p)) continue
            am().killBackgroundProcesses(p); count++
        }
        System.gc()
        Thread.sleep(700)
        val after = memInfo()["avail"] as Long
        return mapOf("killed" to count, "freed" to (after - before).coerceAtLeast(0))
    }

    // ---------- Do Not Disturb (no notifications popping up mid-match)
    private fun setDnd(on: Boolean): Boolean {
        val n = nm()
        if (!n.isNotificationPolicyAccessGranted) return false
        if (on) {
            if (savedDndFilter == null) savedDndFilter = n.currentInterruptionFilter
            n.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_PRIORITY)
        } else {
            n.setInterruptionFilter(savedDndFilter ?: NotificationManager.INTERRUPTION_FILTER_ALL)
            savedDndFilter = null
        }
        return true
    }

    /**
     * Locks the SYSTEM screen rotation while gaming so the screen can't flip by accident.
     * mode = "portrait" | "landscape" | "off" (restore previous setting).
     * Needs "Modify system settings" permission (user grants once).
     * Note: a game that forces its own orientation always wins.
     */
    private fun lockRotation(mode: String): Boolean {
        if (!Settings.System.canWrite(this)) return false
        val cr = contentResolver
        return try {
            if (mode == "off") {
                savedAutoRotate?.let { Settings.System.putInt(cr, Settings.System.ACCELEROMETER_ROTATION, it) }
                savedUserRotation?.let { Settings.System.putInt(cr, Settings.System.USER_ROTATION, it) }
                savedAutoRotate = null; savedUserRotation = null
            } else {
                if (savedAutoRotate == null) {
                    savedAutoRotate = Settings.System.getInt(cr, Settings.System.ACCELEROMETER_ROTATION, 1)
                    savedUserRotation = Settings.System.getInt(cr, Settings.System.USER_ROTATION, 0)
                }
                Settings.System.putInt(cr, Settings.System.ACCELEROMETER_ROTATION, 0)
                Settings.System.putInt(cr, Settings.System.USER_ROTATION,
                    if (mode == "landscape") android.view.Surface.ROTATION_90 else android.view.Surface.ROTATION_0)
            }
            true
        } catch (e: Exception) { false }
    }

    // ---------- floating game bar (overlay over the game while boosting)
    private fun canDrawOverlays(): Boolean =
        Build.VERSION.SDK_INT >= 23 && Settings.canDrawOverlays(this)

    private fun gameBarOn(title: String): Boolean {
        if (!canDrawOverlays()) return false
        if (gameBarView != null) { gameBarSetText("⚡ $title"); return true }
        val tv = TextView(this).apply {
            text = "⚡ $title"
            setTextColor(0xFFEEF0F7.toInt())
            textSize = 13f
            setSingleLine(true)
        }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = GradientDrawable().apply {
                cornerRadius = 28f
                setColor(0xE610131C.toInt())
                setStroke(2, 0xFF8B5CF6.toInt())
            }
            setPadding(48, 30, 48, 30)
            addView(tv)
            setOnClickListener { // tap the bar -> back to ArenaBoost (auto-restores on return)
                val i = packageManager.getLaunchIntentForPackage(packageName)
                if (i != null) {
                    i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_BRING_TO_FRONT)
                    startActivity(i)
                }
            }
        }
        val type = if (Build.VERSION.SDK_INT >= 26)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE
        val p = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        p.gravity = Gravity.TOP or Gravity.START
        p.x = 24
        p.y = 120
        try {
            wm.addView(bar, p)
        } catch (e: Exception) {
            return false
        }
        gameBarView = bar
        gameBarText = tv
        return true
    }

    private fun gameBarOff(): Boolean {
        val v = gameBarView ?: return true
        try { wm.removeView(v) } catch (e: Exception) { /* already gone */ }
        gameBarView = null
        gameBarText = null
        return true
    }

    private fun gameBarSetText(text: String): Boolean {
        val t = gameBarText ?: return false
        t.text = text
        return true
    }

    /** CPU usage % since the previous call (deviceInfo is polled every ~3 s). */
    private fun cpuUsage(): Int {
        return try {
            val line = File("/proc/stat").readText().lineSequence().first { it.startsWith("cpu ") }
            val v = line.split(Regex("\\s+")).drop(1).map { it.toLong() }
            val idle = v[3] + if (v.size > 4) v[4] else 0L
            val total = v.sum()
            val dTotal = total - lastCpuTotal
            val dIdle = idle - lastCpuIdle
            lastCpuTotal = total
            lastCpuIdle = idle
            if (dTotal <= 0) 0 else (100.0 * (dTotal - dIdle) / dTotal).toInt()
        } catch (e: Exception) {
            0
        }
    }

    override fun onDestroy() {
        gameBarOff()
        super.onDestroy()
    }

    // ---------- Android 12+ Game Mode API (read-only for 3rd-party apps)
    private fun gameMode(pkg: String): String {
        if (Build.VERSION.SDK_INT < 31) return "Not supported (Android 12+ needed)"
        return try {
            val gm = getSystemService(GameManager::class.java)
            if (pkg == packageName) {
                when (gm.gameMode) {
                    GameManager.GAME_MODE_PERFORMANCE -> "Performance"
                    GameManager.GAME_MODE_BATTERY -> "Battery"
                    GameManager.GAME_MODE_STANDARD -> "Standard"
                    else -> "Unsupported"
                }
            } else "Set in your phone's Game Dashboard / Game Space"
        } catch (e: Exception) { "Unknown" }
    }

    // ---------- device / thermal / network
    private fun deviceInfo(): Map<String, Any?> {
        val bi = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val temp = (bi?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) ?: 0) / 10.0
        val level = bi?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val plugged = (bi?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
        val pw = getSystemService(Context.POWER_SERVICE) as PowerManager
        val thermal = if (Build.VERSION.SDK_INT >= 29) when (pw.currentThermalStatus) {
            PowerManager.THERMAL_STATUS_NONE -> "Normal"
            PowerManager.THERMAL_STATUS_LIGHT -> "Warm"
            PowerManager.THERMAL_STATUS_MODERATE -> "Hot - throttling likely"
            PowerManager.THERMAL_STATUS_SEVERE -> "Very hot - heavy throttling"
            else -> "CRITICAL - let phone cool"
        } else "Unknown"
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork)
        val net = when {
            caps == null -> "Offline"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Mobile data"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet"
            else -> "Other"
        }
        @Suppress("DEPRECATION")
        val refresh: Float = if (Build.VERSION.SDK_INT >= 30) (display?.refreshRate ?: 60f)
                             else windowManager.defaultDisplay.refreshRate
        val storage = File(filesDir.absolutePath)
        return mapOf(
            "model" to "${Build.MANUFACTURER} ${Build.MODEL}",
            "android" to "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})",
            "cpu" to Build.HARDWARE, "cores" to Runtime.getRuntime().availableProcessors(),
            "cpuUsage" to cpuUsage(),
            "batteryTemp" to temp, "battery" to level, "charging" to plugged,
            "thermal" to thermal, "powerSave" to pw.isPowerSaveMode, "network" to net,
            "refresh" to refresh.toInt(),
            "storageFree" to storage.freeSpace, "storageTotal" to storage.totalSpace
        )
    }
}
