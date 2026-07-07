package com.hermes.chat

import android.content.Context
import android.content.SharedPreferences

class SettingsManager(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("hermes_chat_prefs", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", DEFAULT_URL) ?: DEFAULT_URL
        set(value) = prefs.edit().putString("server_url", value).apply()

    var sessionId: String
        get() = prefs.getString("session_id", "") ?: ""
        set(value) = prefs.edit().putString("session_id", value).apply()

    var isDarkTheme: Boolean
        get() = prefs.getBoolean("dark_theme", true)
        set(value) = prefs.edit().putBoolean("dark_theme", value).apply()

    fun clearSession() {
        prefs.edit().remove("session_id").apply()
    }

    companion object {
        const val DEFAULT_URL = "http://127.0.0.1:8765"
    }
}
