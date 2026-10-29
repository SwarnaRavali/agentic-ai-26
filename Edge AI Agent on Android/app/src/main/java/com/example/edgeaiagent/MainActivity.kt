package com.example.edgeaiagent

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import com.example.edgeaiagent.ui.theme.EdgeAIAgentTheme

// FILE INFO: The main activity, the app's first and only screen.
// It just shows the chat: see ChatScreen(viewModel) in setContent below
class MainActivity : ComponentActivity() {
    private val viewModel: ChatViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT))
        setContent {
            EdgeAIAgentTheme {
                ChatScreen(viewModel)
            }
        }
    }
}
