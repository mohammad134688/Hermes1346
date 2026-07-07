package com.hermes.chat

import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
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
            itemAnimator = null  // Smoother without animation
        }
    }

    private fun setupClickListeners() {
        btnSend.setOnClickListener {
            sendMessage()
        }

        btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        editMessage.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                sendMessage()
                true
            } else false
        }

        // Scroll to bottom when keyboard appears
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

    private fun sendMessage() {
        val message = editMessage.text?.toString()?.trim() ?: return
        if (message.isEmpty() || isSending) return

        isSending = true
        editMessage.text?.clear()
        btnSend.isEnabled = false

        // Add user message
        chatAdapter.addMessage(ChatMessage(content = message, isUser = true))
        scrollToBottom()

        // Show typing indicator
        showTyping(true)

        // Send to Hermes
        lifecycleScope.launch {
            val response = hermesClient.sendMessage(message)

            showTyping(false)
            isSending = false
            btnSend.isEnabled = true

            when {
                response.error == "connection_error" -> {
                    chatAdapter.addMessage(
                        ChatMessage(
                            content = "⚠️ خطا در اتصال به سرور!\n\nلطفاً مطمئن شوید bridge server در Termux در حال اجراست:\n\n`nohup python3 hermes_bridge.py &`",
                            isUser = false,
                            isError = true
                        )
                    )
                }
                response.error == "timeout" -> {
                    chatAdapter.addMessage(
                        ChatMessage(
                            content = "⏱️ پاسخ دیر شد. Hermes ممکن است مشغول اجرای ابزار باشد.",
                            isUser = false,
                            isError = true
                        )
                    )
                }
                response.success && response.response.isNotEmpty() -> {
                    // Save session ID
                    if (response.sessionId.isNotEmpty()) {
                        settingsManager.sessionId = response.sessionId
                    }
                    chatAdapter.addMessage(
                        ChatMessage(content = response.response, isUser = false)
                    )
                }
                else -> {
                    chatAdapter.addMessage(
                        ChatMessage(
                            content = response.error ?: "پاسخ خالی دریافت شد",
                            isUser = false,
                            isError = true
                        )
                    )
                }
            }

            scrollToBottom()
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
                delay(5000) // Check every 5 seconds
            }
        }
    }

    private suspend fun checkServerStatus() {
        val isOnline = hermesClient.checkStatus()
        val dot = statusDot.background as? GradientDrawable

        runOnUiThread {
            if (isOnline) {
                statusText.text = getString(R.string.connected)
                dot?.setColor(getColor(R.color.status_connected))
            } else {
                statusText.text = getString(R.string.disconnected)
                dot?.setColor(getColor(R.color.status_disconnected))
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (statusCheckJob == null) {
            startStatusChecker()
        }
    }

    override fun onPause() {
        super.onPause()
        statusCheckJob?.cancel()
        statusCheckJob = null
    }
}
