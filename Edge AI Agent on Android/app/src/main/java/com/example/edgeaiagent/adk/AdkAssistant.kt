package com.example.edgeaiagent.adk

import android.content.Context
import android.util.Log
import com.example.edgeaiagent.Assistant
import com.example.edgeaiagent.SYSTEM_PROMPT
import com.example.edgeaiagent.TAG
import com.example.edgeaiagent.TOOL_RULE
import com.example.edgeaiagent.loadEngine
import com.google.adk.kt.agents.Instruction
import com.google.adk.kt.agents.LlmAgent
import com.google.adk.kt.litertlm.LiteRtLmModel
import com.google.adk.kt.runners.InMemoryRunner
import com.google.adk.kt.sessions.SessionKey
import com.google.adk.kt.types.Content
import com.google.adk.kt.types.Role
import com.google.ai.edge.litertlm.Engine

private const val APP_NAME = "buddy"
private const val USER_ID = "user"
private const val SESSION_ID = "chat"

// POINT TO LOOK: The most model calls per message, so a tool loop always ends
private const val MAX_STEPS = 3

// FILE INFO: Stage 2, a single AI agent built with Google ADK.
// It chats with us and calls the time tool when asked about the date or time
class AdkAssistant(private val context: Context) : Assistant {
    // AI AGENT COMPONENT: The engine runs the Gemma model on the phone (LiteRT-LM)
    private var engine: Engine? = null
    // AI AGENT COMPONENT: ADK's adapter, so an ADK agent can use the on-device engine
    private var model: LiteRtLmModel? = null
    // AI AGENT COMPONENT: The runner runs the agent and keeps the conversation in memory
    private var runner: InMemoryRunner? = null

    // AI AGENT METHOD: Loads the model, builds the agent and opens one chat session
    override suspend fun start(): String {
        val (eng, backendName) = loadEngine(context)
        val llm = LiteRtLmModel.create(eng)

        // AI AGENT: The agent: a model, an instruction (system prompt + tool rule) and the tools it may call
        val agent = LlmAgent(
            name = "buddy",
            model = llm,
            instruction = Instruction("$SYSTEM_PROMPT $TOOL_RULE"),
            tools = listOf(TimeTool()),
            maxSteps = MAX_STEPS,
        )
        val r = InMemoryRunner(agent = agent, appName = APP_NAME)
        r.sessionService.createSession(SessionKey(APP_NAME, USER_ID, SESSION_ID))

        engine = eng
        model = llm
        runner = r
        Log.i(TAG, "Backend in use: $backendName (via ADK)")
        return "$backendName · ADK"
    }

    // AI AGENT METHOD: Sends the message to the agent and reports each step to the screen
    override suspend fun chat(text: String, onStep: (String) -> Unit): String {
        val r = checkNotNull(runner) { "Model not loaded yet" }
        onStep("model: thinking…")

        var answer = ""
        // POINT TO LOOK: The runner streams events: tool calls, tool results and finally the answer
        r.runAsync(userId = USER_ID, sessionId = SESSION_ID, newMessage = Content.fromText(Role.USER, text))
            .collect { event ->
                event.functionCalls().forEach { onStep("tool call: ${it.name}(${it.args})") }
                event.functionResponses().forEach { onStep("tool ${it.name} -> ${it.response}") }
                event.errorMessage?.let { onStep("error: $it") }
                if (event.isFinalResponse) answer = event.content?.text().orEmpty()
            }
        return answer.ifEmpty { "Sorry, I could not finish: no answer after $MAX_STEPS steps." }
    }

    // AI AGENT METHOD: Frees the runner, the model and the engine
    override fun close() {
        runner?.close()
        model?.close()
        engine?.close()
        runner = null
        model = null
        engine = null
    }
}
