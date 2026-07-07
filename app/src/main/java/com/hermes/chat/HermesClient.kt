package com.hermes.chat

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

class HermesClient(private val settings: SettingsManager) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()

    data class ChatResponse(
        val response: String,
        val sessionId: String,
        val success: Boolean,
        val error: String? = null
    )

    interface StreamCallback {
        fun onChunk(text: String)
        fun onComplete(response: String, sessionId: String, success: Boolean, error: String?)
    }

    /**
     * Send a message and stream the response via SSE.
     */
    suspend fun sendMessageStream(
        message: String,
        callback: StreamCallback
    ) = withContext(Dispatchers.IO) {
        try {
            val jsonBody = JSONObject().apply {
                put("message", message)
                put("session_id", settings.sessionId)
            }

            val request = Request.Builder()
                .url("${settings.serverUrl}/chat/stream")
                .post(jsonBody.toString().toRequestBody("application/json".toMediaType()))
                .build()

            val response = client.newCall(request).execute()
            try {
                if (!response.isSuccessful) {
                    callback.onComplete("", settings.sessionId, false, "http_${response.code}")
                    return@withContext
                }

                val body = response.body
                if (body == null) {
                    callback.onComplete("", settings.sessionId, false, "empty_body")
                    return@withContext
                }

                val reader = BufferedReader(InputStreamReader(body.byteStream()))
                var currentEvent = ""
                var fullResponse = ""

                try {
                    while (true) {
                        val line = reader.readLine() ?: break
                        when {
                            line.startsWith("event: ") -> {
                                currentEvent = line.removePrefix("event: ").trim()
                            }
                            line.startsWith("data: ") -> {
                                val data = line.removePrefix("data: ").trim()
                                if (data == "[DONE]") break

                                try {
                                    val json = JSONObject(data)
                                    when (currentEvent) {
                                        "chunk" -> {
                                            val text = json.optString("text", "")
                                            if (text.isNotEmpty()) {
                                                fullResponse += text
                                                try {
                                                    callback.onChunk(text)
                                                } catch (_: Exception) { }
                                            }
                                        }
                                        "done" -> {
                                            val finalResponse = json.optString("response", fullResponse)
                                            val sessionId = json.optString("session_id", settings.sessionId)
                                            val success = json.optBoolean("success", false)
                                            val error = json.optString("error", "").ifEmpty { null }
                                            callback.onComplete(finalResponse, sessionId, success, error)
                                            return@withContext
                                        }
                                    }
                                } catch (_: Exception) { }
                            }
                        }
                    }
                } catch (_: Exception) { }

                // Fallback if no "done" event received
                callback.onComplete(fullResponse, settings.sessionId, true, null)

            } finally {
                try { response.close() } catch (_: Exception) { }
            }

        } catch (e: java.net.ConnectException) {
            callback.onComplete("", settings.sessionId, false, "connection_error")
        } catch (e: java.util.concurrent.TimeoutException) {
            callback.onComplete("", settings.sessionId, false, "timeout")
        } catch (e: Exception) {
            callback.onComplete("", settings.sessionId, false, e.message ?: "unknown_error")
        }
    }

    /**
     * One-shot send (non-streaming). Fallback.
     */
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
            ChatResponse(response = "", sessionId = settings.sessionId, success = false, error = "connection_error")
        } catch (e: java.util.concurrent.TimeoutException) {
            ChatResponse(response = "", sessionId = settings.sessionId, success = false, error = "timeout")
        } catch (e: Exception) {
            ChatResponse(response = "", sessionId = settings.sessionId, success = false, error = e.message ?: "unknown_error")
        }
    }

    suspend fun checkStatus(): Boolean = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("${settings.serverUrl}/status")
                .get()
                .build()
            val response = client.newCall(request).execute()
            val result = response.isSuccessful
            response.close()
            result
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
                response.close()
                true
            } else {
                response.close()
                false
            }
        } catch (e: Exception) {
            false
        }
    }
}
