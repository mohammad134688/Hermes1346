package com.hermes.chat

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.launch

class SettingsActivity : AppCompatActivity() {

    private lateinit var settingsManager: SettingsManager
    private lateinit var editServerUrl: TextInputEditText
    private lateinit var btnTestConnection: MaterialButton
    private lateinit var toolbar: MaterialToolbar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        settingsManager = SettingsManager(this)

        toolbar = findViewById(R.id.toolbar)
        editServerUrl = findViewById(R.id.editServerUrl)
        btnTestConnection = findViewById(R.id.btnTestConnection)

        toolbar.setNavigationOnClickListener { finish() }

        // Load current settings
        editServerUrl.setText(settingsManager.serverUrl)

        btnTestConnection.setOnClickListener {
            testConnection()
        }
    }

    override fun onPause() {
        super.onPause()
        // Save settings when leaving
        val url = editServerUrl.text?.toString()?.trim()
        if (!url.isNullOrEmpty()) {
            settingsManager.serverUrl = url
        }
    }

    private fun testConnection() {
        val url = editServerUrl.text?.toString()?.trim()
        if (url.isNullOrEmpty()) {
            Toast.makeText(this, getString(R.string.enter_server_url), Toast.LENGTH_SHORT).show()
            return
        }

        settingsManager.serverUrl = url
        btnTestConnection.isEnabled = false
        btnTestConnection.text = getString(R.string.testing)

        lifecycleScope.launch {
            val client = HermesClient(settingsManager)
            val isOnline = client.checkStatus()

            runOnUiThread {
                btnTestConnection.isEnabled = true
                btnTestConnection.text = getString(R.string.test_connection)

                if (isOnline) {
                    Toast.makeText(
                        this@SettingsActivity,
                        "✅ اتصال موفق!",
                        Toast.LENGTH_SHORT
                    ).show()
                } else {
                    Toast.makeText(
                        this@SettingsActivity,
                        getString(R.string.connection_failed),
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }
}
