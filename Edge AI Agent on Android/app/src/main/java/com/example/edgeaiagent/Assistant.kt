package com.example.edgeaiagent

// LOGGING: Every log line uses this tag; filter Logcat by "HelloAgent" to follow the agent
const val TAG = "HelloAgent"

// AI PROMPT: The system prompt, which gives the model its role and tone
const val SYSTEM_PROMPT =
    "You are Buddy, a warm and easygoing friend to chat with. " +
        "Keep replies short and natural, like texting a friend. " +
        "You can also tell people the current time."

// AI PROMPT: The model gets a tool that returns the current time;
// this rule tells it when to use that tool instead of guessing
const val TOOL_RULE =
    "You cannot know the current date or time. For ANY question about the date or time, " +
        "you must call the time tool; never guess."

// AI AGENT COMPONENT: The template every assistant follows.
// Why: the chat screen talks only to this interface, so we can swap
// one assistant for another (echo, single agent, multi-agent) in one line
interface Assistant {
    // AI AGENT METHOD: Loads the model and gets the assistant ready.
    // Returns a short label (e.g. "GPU · Tutor") shown at the top of the chat
    suspend fun start(): String

    // AI AGENT METHOD: Handles one user message and returns the reply.
    // onStep reports each step while the model works (tool calls, agent switches).
    // Those steps go to ChatViewModel.addStep (logged to Logcat) and
    // appear in the "Behind the scenes" card (StepsCard in ChatScreen.kt)
    suspend fun chat(text: String, onStep: (String) -> Unit): String

    // AI AGENT METHOD: Frees the model and engine when the app closes
    fun close()
}

// AI AGENT EXCEPTION: Thrown when the model file is not in the app's data folder;
// pushCommand is the adb command that copies it onto the phone
class ModelMissingException(val pushCommand: String) : Exception()

// AI AGENT IMPLEMENTATION: First exercise: reply with the user's own message,
// to check that the chat works before adding a model
class EchoAssistant : Assistant {
    override suspend fun start(): String = "Echo"

    override suspend fun chat(text: String, onStep: (String) -> Unit): String = text

    override fun close() {}
}
