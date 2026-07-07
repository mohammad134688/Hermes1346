package com.hermes.chat

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class HermesClient(private val settings: SettingsManager) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)  // Hermes can take a while
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()

    data class ChatResponse(
        val response: String,
        val sessionId: String,
        val success: Boolean,
        val error: String? = null
    )

    suspend fun sendMessage(message: String): ChatResponse = withContext(Dispatchers.IO) {
        try {
            val jsonBody = JSONObject().apply {
                put("message", message)
                put("session_id", settings.sessionId)
            }

            val request = Request.Builder()
                .url("${settings.serverUrl}/chat")
                .post(jsonBody.toString().toRequestBody("application/json".toMediaType()))
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: throw Exception("Empty response")

            val json = JSONObject(body)
            ChatResponse(
                response = json.optString("response", ""),
                sessionId = json.optString("session_id", settings.sessionId),
                success = json.optBoolean("success", false),
                error = json.optString("error", null)
            )
        } catch (e: java.net.ConnectException) {
            ChatResponse(
                response = "",
                sessionId = settings.sessionId,
                success = false,
                error = "connection_error"
            )
        } catch (e: java.util.concurrent.TimeoutException) {
            ChatResponse(
                response = "",
                sessionId = settings.sessionId,
                success = false,
                error = "timeout"
            )
        } catch (e: Exception) {
            ChatResponse(
                response = "",
                sessionId = settings.sessionId,
                success = false,
                error = e.message ?: "unknown_error"
            )
        }
    }

    suspend fun checkStatus(): Boolean = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("${settings.serverUrl}/status")
                .get()
                .build()

            val response = client.newCall(request).execute()
            response.isSuccessful
        } catch (e: Exception) {
            false
        }
    }

    suspend fun newSession(): Boolean = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("${settings.serverUrl}/new")
                .post("{}".toRequestBody("application/json".toMediaType()))
                .build()

            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                settings.clearSession()
                true
            } else false
        } catch (e: Exception) {
            false
        }
    }
}
