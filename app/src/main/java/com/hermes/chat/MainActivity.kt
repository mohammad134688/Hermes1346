package com.hermes.chat

import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.ImageButton
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.floatingactionbutton.FloatingActionButton
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var editMessage: EditText
    private lateinit var btnSend: FloatingActionButton
    private lateinit var btnSettings: ImageButton
    private lateinit var typingIndicator: View
    private lateinit var statusDot: View
    private lateinit var statusText: android.widget.TextView

    private lateinit var chatAdapter: ChatAdapter
    private lateinit var settingsManager: SettingsManager
    private lateinit var hermesClient: HermesClient
    private var isSending = false
    private var statusCheckJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        settingsManager = SettingsManager(this)
        hermesClient = HermesClient(settingsManager)

        initViews()
        setupRecyclerView()
        setupClickListeners()
        showWelcomeMessage()
        startStatusChecker()
    }

    private fun initViews() {
        recyclerView = findViewById(R.id.recyclerChat)
        editMessage = findViewById(R.id.editMessage)
        btnSend = findViewById(R.id.btnSend)
        btnSettings = findViewById(R.id.btnSettings)
        typingIndicator = findViewById(R.id.typingIndicator)
        statusDot = findViewById(R.id.statusDot)
        statusText = findViewById(R.id.statusText)
    }

    private fun setupRecyclerView() {
        chatAdapter = ChatAdapter()
        val layoutManager = LinearLayoutManager(this).apply {
            stackFromEnd = true
        }
        recyclerView.apply {
            this.layoutManager = layoutManager
            adapter = chatAdapter
            itemAnimator = null
        }
    }

    private fun setupClickListeners() {
        btnSend.setOnClickListener { sendMessage() }
        btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        editMessage.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                sendMessage()
                true
            } else false
        }
        recyclerView.addOnLayoutChangeListener { _, _, _, _, bottom, _, _, _, oldBottom ->
            if (bottom < oldBottom) {
                recyclerView.post {
                    recyclerView.smoothScrollToPosition(chatAdapter.itemCount - 1)
                }
            }
        }
    }

    private fun showWelcomeMessage() {
        chatAdapter.addMessage(
            ChatMessage(
                content = getString(R.string.welcome_message),
                isUser = false
            )
        )
    }

    @Volatile
    private var streamingBotAdded = false

    private fun sendMessage() {
        val message = editMessage.text?.toString()?.trim() ?: return
        if (message.isEmpty() || isSending) return

        isSending = true
        streamingBotAdded = false
        editMessage.text?.clear()
        btnSend.isEnabled = false

        chatAdapter.addMessage(ChatMessage(content = message, isUser = true))
        scrollToBottom()
        showTyping(true)

        lifecycleScope.launch {
            hermesClient.sendMessageStream(message, object : HermesClient.StreamCallback {
                override fun onChunk(text: String) {
                    try {
                        runOnUiThread {
                            try {
                                // Add empty bot message on first chunk only
                                if (!streamingBotAdded) {
                                    streamingBotAdded = true
                                    chatAdapter.addMessage(ChatMessage(content = "", isUser = false))
                                }
                                chatAdapter.appendToLastMessage(text)
                                scrollToBottom()
                            } catch (e: Exception) {
                                Log.e("HermesChat", "Chunk UI error: ${e.message}")
                            }
                        }
                    } catch (_: Exception) { }
                }

                override fun onComplete(
                    response: String,
                    sessionId: String,
                    success: Boolean,
                    error: String?
                ) {
                    try {
                        runOnUiThread {
                            try {
                                showTyping(false)
                                isSending = false
                                btnSend.isEnabled = true

                                when {
                                    error == "connection_error" -> {
                                        // Only remove if we added an empty bot message
                                        if (streamingBotAdded) {
                                            chatAdapter.removeLastMessage()
                                        }
                                        chatAdapter.addMessage(
                                            ChatMessage(
                                                content = getString(R.string.error_server),
                                                isUser = false,
                                                isError = true
                                            )
                                        )
                                    }
                                    error == "timeout" -> {
                                        if (streamingBotAdded) {
                                            chatAdapter.removeLastMessage()
                                        }
                                        chatAdapter.addMessage(
                                            ChatMessage(
                                                content = getString(R.string.response_timeout),
                                                isUser = false,
                                                isError = true
                                            )
                                        )
                                    }
                                    success && response.isNotEmpty() -> {
                                        if (sessionId.isNotEmpty()) {
                                            settingsManager.sessionId = sessionId
                                        }
                                        // Update the streaming message with final clean response
                                        if (streamingBotAdded) {
                                            chatAdapter.updateLastMessage(response)
                                        } else {
                                            chatAdapter.addMessage(
                                                ChatMessage(content = response, isUser = false)
                                            )
                                        }
                                    }
                                    else -> {
                                        if (streamingBotAdded) {
                                            chatAdapter.removeLastMessage()
                                        }
                                        chatAdapter.addMessage(
                                            ChatMessage(
                                                content = error ?: getString(R.string.empty_response),
                                                isUser = false,
                                                isError = true
                                            )
                                        )
                                    }
                                }
                                scrollToBottom()
                            } catch (e: Exception) {
                                Log.e("HermesChat", "Complete UI error: ${e.message}")
                                isSending = false
                                btnSend.isEnabled = true
                            }
                        }
                    } catch (_: Exception) {
                        isSending = false
                    }
                }
            })
        }
    }

    private fun showTyping(show: Boolean) {
        typingIndicator.visibility = if (show) View.VISIBLE else View.GONE
        if (show) scrollToBottom()
    }

    private fun scrollToBottom() {
        recyclerView.post {
            if (chatAdapter.itemCount > 0) {
                recyclerView.smoothScrollToPosition(chatAdapter.itemCount - 1)
            }
        }
    }

    private fun startStatusChecker() {
        statusCheckJob = lifecycleScope.launch {
            while (true) {
                checkServerStatus()
                delay(5000)
            }
        }
    }

    private suspend fun checkServerStatus() {
        try {
            val isOnline = hermesClient.checkStatus()
            val dot = statusDot.background as? GradientDrawable
            runOnUiThread {
                try {
                    if (isOnline) {
                        statusText.text = getString(R.string.connected)
                        dot?.setColor(getColor(R.color.status_connected))
                    } else {
                        statusText.text = getString(R.string.disconnected)
                        dot?.setColor(getColor(R.color.status_disconnected))
                    }
                } catch (_: Exception) { }
            }
        } catch (_: Exception) { }
    }

    override fun onResume() {
        super.onResume()
        if (statusCheckJob == null) startStatusChecker()
    }

    override fun onPause() {
        statusCheckJob?.cancel()
        statusCheckJob = null
    }
}
