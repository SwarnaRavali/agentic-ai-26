package com.example.edgeaiagent

import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private class ChatColors    (
    val background: Color,
    val header: Color,
    val botBubble: Color,
    val botText: Color,
    val noteBackground: Color,
    val noteText: Color,
)

private val LightColors = ChatColors(
    background = Color(0xFFEEF1FF),
    header = Color(0xFF4F46E5),
    botBubble = Color.White,
    botText = Color(0xFF1F2937),
    noteBackground = Color(0xFFDDE3FF),
    noteText = Color(0xFF4B5563),
)

private val DarkColors = ChatColors(
    background = Color(0xFF111827),
    header = Color(0xFF3730A3),
    botBubble = Color(0xFF1F2937),
    botText = Color(0xFFF3F4F6),
    noteBackground = Color(0xFF1E293B),
    noteText = Color(0xFF9CA3AF),
)

private val Indigo = Color(0xFF6366F1)
private val UserGradient = Brush.horizontalGradient(listOf(Indigo, Color(0xFF8B5CF6)))

// FILE INFO: The chat screen and its look: the header, the message bubbles,
// the "Behind the scenes" steps card, and the input box with the send button
@Composable
fun ChatScreen(viewModel: ChatViewModel) {
    val colors = if (isSystemInDarkTheme()) DarkColors else LightColors
    val state by viewModel.state.collectAsState()
    val messages by viewModel.messages.collectAsState()
    val generating by viewModel.generating.collectAsState()
    val replyStats by viewModel.replyStats.collectAsState()
    val steps by viewModel.steps.collectAsState()
    var input by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    val itemCount = messages.size + if (steps.isEmpty()) 0 else 1
    LaunchedEffect(itemCount, steps.size) {
        if (itemCount > 0) listState.scrollToItem(itemCount - 1)
    }

    Column(Modifier.fillMaxSize().background(colors.background).imePadding()) {
        Column(
            Modifier.fillMaxWidth().background(colors.header).statusBarsPadding()
                .padding(horizontal = 16.dp, vertical = 12.dp)
        ) {
            Text("Buddy", color = Color.White, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            val status = when (val s = state) {
                UiState.Loading -> "Loading model…"
                is UiState.Ready -> "Backend: ${s.backend} · init ${s.initMs} ms"
                is UiState.Error -> "Error"
                is UiState.ModelMissing -> "Model missing"
            }
            Text(status, color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.labelMedium)
            if (replyStats.isNotEmpty()) {
                Text(replyStats, color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.labelSmall)
            }
        }

        when (val s = state) {
            is UiState.ModelMissing -> Notice(
                "Run the app once, then push the model:\n${s.pushCommand}",
                colors.noteText,
                colors,
            )
            is UiState.Error -> Notice(s.message, Color(0xFFE5484D), colors)
            else -> {}
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (messages.isEmpty() && state is UiState.Ready) {
                item { Text("Say hi! Chat about anything, or ask me what time it is.", color = colors.noteText) }
            }
            items(messages) { Bubble(it, colors) }
            if (steps.isNotEmpty()) item { StepsCard(steps, colors) }
        }

        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Message…", color = colors.noteText) },
                maxLines = 4,
                shape = RoundedCornerShape(24.dp),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = colors.botBubble,
                    unfocusedContainerColor = colors.botBubble,
                    focusedTextColor = colors.botText,
                    unfocusedTextColor = colors.botText,
                    cursorColor = Indigo,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                ),
            )
            Button(
                onClick = {
                    viewModel.send(input)
                    input = ""
                },
                enabled = state is UiState.Ready && !generating && input.isNotBlank(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Indigo,
                    contentColor = Color.White,
                    disabledContainerColor = Indigo.copy(alpha = 0.35f),
                    disabledContentColor = Color.White.copy(alpha = 0.8f),
                ),
            ) { Text("Send") }
        }
    }
}

@Composable
private fun Bubble(message: ChatMessage, colors: ChatColors) {
    val fromUser = message.fromUser
    val shape = RoundedCornerShape(18.dp, 18.dp, if (fromUser) 4.dp else 18.dp, if (fromUser) 18.dp else 4.dp)
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = if (fromUser) Arrangement.End else Arrangement.Start,
    ) {
        Text(
            text = message.text,
            color = if (fromUser) Color.White else colors.botText,
            modifier = Modifier
                .widthIn(max = 300.dp)
                .then(
                    if (fromUser) Modifier.background(UserGradient, shape)
                    else Modifier.background(colors.botBubble, shape)
                )
                .padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
}

// POINT TO LOOK: Where onStep ends up: every step the assistant reports
// (via ChatViewModel.addStep) is listed in this "Behind the scenes" card
@Composable
private fun StepsCard(steps: List<String>, colors: ChatColors) {
    Column(
        Modifier.fillMaxWidth()
            .background(colors.noteBackground, RoundedCornerShape(12.dp))
            .padding(10.dp)
    ) {
        Text("Behind the scenes", color = colors.noteText, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        steps.forEach {
            Text(it, color = colors.noteText, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
private fun Notice(text: String, textColor: Color, colors: ChatColors) {
    Text(
        text,
        color = textColor,
        modifier = Modifier.padding(12.dp).fillMaxWidth()
            .background(colors.noteBackground, RoundedCornerShape(12.dp))
            .padding(12.dp),
    )
}
