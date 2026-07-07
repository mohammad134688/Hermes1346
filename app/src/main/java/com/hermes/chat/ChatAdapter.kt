package com.hermes.chat

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class ChatAdapter : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    private val messages = mutableListOf<ChatMessage>()

    companion object {
        private const val TYPE_USER = 0
        private const val TYPE_BOT = 1
    }

    class UserViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val textMessage: TextView = view.findViewById(R.id.textMessage)
        val textTime: TextView = view.findViewById(R.id.textTime)
    }

    class BotViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val textMessage: TextView = view.findViewById(R.id.textMessage)
        val textTime: TextView = view.findViewById(R.id.textTime)
    }

    override fun getItemViewType(position: Int): Int {
        return if (messages[position].isUser) TYPE_USER else TYPE_BOT
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        return if (viewType == TYPE_USER) {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_message_user, parent, false)
            UserViewHolder(view)
        } else {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_message_bot, parent, false)
            BotViewHolder(view)
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        val message = messages[position]

        when (holder) {
            is UserViewHolder -> {
                holder.textMessage.text = message.content
                holder.textTime.text = message.formattedTime()
            }
            is BotViewHolder -> {
                holder.textMessage.text = renderMarkdown(message.content)
                holder.textTime.text = message.formattedTime()
            }
        }
    }

    override fun getItemCount() = messages.size

    fun addMessage(message: ChatMessage) {
        messages.add(message)
        notifyItemInserted(messages.size - 1)
    }

    fun removeLastMessage() {
        if (messages.isNotEmpty()) {
            val last = messages.size - 1
            messages.removeAt(last)
            notifyItemRemoved(last)
        }
    }

    fun getLastMessage(): ChatMessage? = messages.lastOrNull()

    fun clear() {
        val size = messages.size
        messages.clear()
        notifyItemRangeRemoved(0, size)
    }

    private fun renderMarkdown(text: String): String {
        // Basic markdown rendering for Android TextView
        // Convert **bold** and *italic* and `code`
        var result = text

        // Handle code blocks first (```...```)
        result = result.replace(Regex("```([\\s\\S]*?)```")) { match ->
            "\n${match.groupValues[1].trim()}\n"
        }

        // Handle inline code
        result = result.replace(Regex("`([^`]+)`")) { match ->
            match.groupValues[1]
        }

        // Handle bold
        result = result.replace(Regex("\\*\\*([^*]+)\\*\\*")) { match ->
            match.groupValues[1]
        }

        // Handle italic
        result = result.replace(Regex("\\*([^*]+)\\*")) { match ->
            match.groupValues[1]
        }

        // Handle strikethrough
        result = result.replace(Regex("~~([^~]+)~~")) { match ->
            match.groupValues[1]
        }

        return result
    }
}
