package com.example.edgeaiagent.tutor

import android.content.Context
import android.util.Log
import com.example.edgeaiagent.Assistant
import com.example.edgeaiagent.TAG
import com.example.edgeaiagent.loadEngine
import com.google.adk.kt.agents.Instruction
import com.google.adk.kt.agents.LlmAgent
import com.google.adk.kt.agents.RunConfig
import com.google.adk.kt.callbacks.AfterModelCallback
import com.google.adk.kt.callbacks.OnModelErrorCallback
import com.google.adk.kt.litertlm.LiteRtLmModel
import com.google.adk.kt.models.LlmResponse
import com.google.adk.kt.runners.InMemoryRunner
import com.google.adk.kt.sessions.SessionKey
import com.google.adk.kt.types.Content
import com.google.adk.kt.types.FunctionCall
import com.google.adk.kt.types.Part
import com.google.adk.kt.types.Role
import com.google.ai.edge.litertlm.Engine
import java.io.File

private const val APP_NAME = "tutor"
private const val USER_ID = "student"
private const val SESSION_ID = "quiz"

// AI MEMORY: The student's latest message travels to the grader under this name
const val STUDENT_ANSWER = "student_answer"

// AI PROMPT: Who the tutor is; one of the rules below is added for the current moment
const val TUTOR_PERSONA =
    "You are Tutor, a friendly English teacher running a short quiz. " +
        "You never ask, answer or grade quiz questions yourself; your helpers do that."

// AI PROMPT: A question is waiting, so the message is an answer
const val TUTOR_WHEN_WAITING =
    "The student was just asked a quiz question, so their message is their answer: call grader. " +
        "'I don't know', 'not sure', 'no idea', 'skip' or a guess are answers too: call grader. " +
        "Only if they clearly want to end the quiz (stop, quit, enough, I'm done, bye): call performance_summary."

// AI PROMPT: No question is waiting, so ask, stop or explain the last answer
const val TUTOR_WHEN_READY =
    "No question is waiting. If the student is ready (yes, ok, sure, next, start, go): call quizmaster. " +
        "If they want to stop (no, stop, quit, enough, I'm done, bye): call performance_summary. " +
        "If they ask about or disagree with their last answer, explain it in one or two kind lines " +
        "using the last result below, then ask if they are ready for the next question. " +
        "Otherwise reply in one short line and ask if they are ready for a question."

// AI PROMPT: All questions are answered
const val TUTOR_WHEN_DONE =
    "The quiz is over. Call performance_summary."

// AI PROMPT: The results are in, so write the closing brief
const val TUTOR_AFTER_SUMMARY =
    "Do not greet or introduce yourself. " +
        "Write a short, warm brief of the results: the score, what went well (name the questions in answered_right), " +
        "and what to practise (name each item in to_practise; if it is empty, say there is nothing to fix). " +
        "Say goodbye. Do not call a tool."

// AI PROMPT: After the brief, answer questions about the results
const val TUTOR_FINISHED =
    "The quiz is over and the student already has their results. Do not call a tool. " +
        "If they ask about their results, answer in one or two lines from the results below, naming the actual items. " +
        "If they say goodbye, say goodbye warmly. Otherwise reply in one short line."

// GUARDRAIL: Only these words may end the quiz while a question is waiting
val STOP_WORDS = listOf("stop", "quit", "enough", "i'm done", "im done", "bye", "end the quiz", "finish")

// AI PROMPT: The quizmaster asks the question its tool returns
const val QUIZMASTER_RULES =
    "You are the quizmaster. First call next_question. " +
        "If it returns done, say in one line that the quiz is finished. " +
        "Otherwise ask exactly the question it returned, as 'Q<number>: <question>'. Never give the answer."

// AI PROMPT: Grader step 1: judge the answer and save the result
const val GRADER_RULES =
    "You are the grader. Compare the student's answer with the reference answer; " +
        "small spelling slips are fine, and a word with the same meaning as a reference word is correct. " +
        "If the student says they don't know, is not sure or skips, the verdict is wrong and the tip gives the right answer. " +
        "Call save_analysis now with your verdict and one short tip."

// AI PROMPT: Grader step 2: reply to the student
const val GRADER_REPLY =
    "You are the grader. The answer is saved. Write one or two short, kind lines to the student, in the present tense."

// GUARDRAIL: Code picks how the reply opens, so it always matches the saved verdict
val VERDICT_OPENINGS = mapOf("correct" to "You are right!", "partly" to "Almost!", "wrong" to "Not quite.")

private val GREETING = Regex("""^(hello|hi|hey)\b[^.!?\n]*[.!?]\s*""", RegexOption.IGNORE_CASE)

// FILE INFO: Stage 3, a multi-agent English tutor.
// The tutor agent decides each turn which helper to call: the grader, the quizmaster or the summary
class TutorAssistant(private val context: Context) : Assistant {
    private var engine: Engine? = null
    private var model: LiteRtLmModel? = null
    private var runner: InMemoryRunner? = null
    // LOGGING: Reports every step, including the helpers', to the screen
    private val reporter = StepReporter()
    // AI MEMORY: The quiz state lives in files, shared by all three agents
    private val log = TutorLog(File(context.filesDir, "tutor"))
    private val summary = PerformanceSummaryTool(log)
    private val rescue = GraderRescue(log) { reporter.onStep(it) }

    // AI AGENT METHOD: Builds the three agents on one shared model and starts a fresh quiz
    override suspend fun start(): String {
        val (eng, backendName) = loadEngine(context)
        // POINT TO LOOK: One model shared by all three agents, so only one copy is in memory
        val llm = LiteRtLmModel.create(eng)

        // AI AGENT: The grader judges the answer, saves it, then replies
        val grader = LlmAgent(
            name = "grader",
            description = "Grades the student's answer to the waiting question and saves the result",
            model = llm,
            instruction = Instruction { ctx -> text(graderStep(ctx.state[STUDENT_ANSWER]?.toString().orEmpty())) },
            tools = listOf(SaveAnalysisTool(log)),
            // GUARDRAIL: Safety nets for when the grader breaks its tool call
            afterModelCallbacks = listOf(AfterModelCallback { _, response -> rescue.afterModel(response) }),
            onModelErrorCallbacks = listOf(OnModelErrorCallback { _, _, error -> rescue.onModelError(error) }),
            includeContents = LlmAgent.IncludeContents.NONE,
            maxSteps = 2,
        )

        // AI AGENT: The quizmaster asks the next question
        val quizmaster = LlmAgent(
            name = "quizmaster",
            description = "Asks the student the next quiz question",
            model = llm,
            instruction = Instruction(QUIZMASTER_RULES),
            tools = listOf(NextQuestionTool(log)),
            includeContents = LlmAgent.IncludeContents.NONE,
            maxSteps = 2,
        )

        // AI AGENT: The tutor, the agent in charge; the other two are its tools
        val tutor = LlmAgent(
            name = "tutor",
            model = llm,
            // AI PROMPT: Rebuilt before every model call with only the rule that fits right now
            instruction = Instruction { ctx -> text("$TUTOR_PERSONA\n\n${tutorRule(ctx.invocationId)}") },
            // POINT TO LOOK: The two helper agents are the tutor's tools. A helper's reply ends the turn
            // (skipSummarization), and isAvailable hides a helper when it does not fit
            tools = listOf(
                AskAgentTool(grader, skipSummarization = true, isAvailable = { log.pending() != null && !quizOver() }) { ctx ->
                    ctx.state[STUDENT_ANSWER]?.toString().orEmpty()
                },
                AskAgentTool(
                    quizmaster,
                    skipSummarization = true,
                    isAvailable = { log.pending() == null && log.analyses().size < QUIZ_LENGTH && !quizOver() },
                ) { _ -> "Ask the next question." },
                summary,
            ),
            // GUARDRAIL: Every tutor reply is checked before ADK acts on it (see guardTutorReply)
            afterModelCallbacks = listOf(
                AfterModelCallback { ctx, response ->
                    guardTutorReply(ctx.state[STUDENT_ANSWER]?.toString().orEmpty(), response)
                }
            ),
            includeContents = LlmAgent.IncludeContents.NONE,
            maxSteps = 3,
        )

        // POINT TO LOOK: The runner gets the reporter, so it also sees the helpers' steps
        val r = InMemoryRunner(agent = tutor, appName = APP_NAME, plugins = listOf(reporter))
        r.sessionService.createSession(SessionKey(APP_NAME, USER_ID, SESSION_ID))
        log.clear()

        engine = eng
        model = llm
        runner = r
        Log.i(TAG, "Backend in use: $backendName (tutor)")
        return "$backendName · Tutor"
    }

    // AI AGENT METHOD: Runs one turn and returns the reply that ended it
    override suspend fun chat(text: String, onStep: (String) -> Unit): String {
        val r = checkNotNull(runner) { "Model not loaded yet" }
        reporter.reset(onStep)
        onStep("model: thinking…")

        var answer = ""
        r.runAsync(
            userId = USER_ID,
            sessionId = SESSION_ID,
            newMessage = Content.fromText(Role.USER, text),
            // AI MEMORY: Hand the message to the grader through the session state
            stateDelta = mapOf(STUDENT_ANSWER to text),
            runConfig = RunConfig(maxLlmCalls = 4),
        ).collect { event ->
            if (!event.isFinalResponse) return@collect
            val helperReply = event.functionResponses().firstOrNull()?.response?.get("result")?.toString()
            answer = helperReply ?: event.content?.text().orEmpty()
        }
        return answer.ifBlank { "Sorry, I could not finish that step. Try again?" }
    }

    // GUARDRAIL: Checks every tutor reply before ADK acts on it.
    // Chatting while an answer waits, or writing a helper's name as text, becomes the right tool call
    private fun guardTutorReply(studentMessage: String, response: LlmResponse): LlmResponse {
        if (response.partial) return response
        if (quizOver()) return withoutGreeting(response)
        val waiting = log.pending() != null
        val calls = response.content?.parts.orEmpty().mapNotNull { it.functionCall?.name }

        if (calls.isNotEmpty()) {
            val wantsToStop = STOP_WORDS.any { studentMessage.lowercase().contains(it) }
            if (!(waiting && "performance_summary" in calls && !wantsToStop)) return response
            reporter.onStep("guard: tutor tried to end the quiz but the student did not ask to stop, calling grader")
            return callTool(response, "grader")
        }

        val said = response.content?.text().orEmpty().trim().trim('`', '.', '"', '\'', '*').trim().lowercase()
        val target = when {
            said == "performance_summary" -> said
            waiting -> "grader"
            log.analyses().size >= QUIZ_LENGTH -> "performance_summary"
            said.startsWith("quizmaster") -> "quizmaster"
            else -> return response
        }
        reporter.onStep("guard: tutor wrote \"${said.take(40)}\" instead of a tool call, calling $target")
        return callTool(response, target)
    }

    // GUARDRAIL: Removes the "Hello!" the model keeps adding to the brief
    private fun withoutGreeting(response: LlmResponse): LlmResponse {
        if (response.content?.parts.orEmpty().any { it.functionCall != null }) return response
        val said = response.content?.text().orEmpty()
        val trimmed = GREETING.replaceFirst(said, "")
        if (trimmed == said || trimmed.isBlank()) return response
        reporter.onStep("guard: removed the greeting from the tutor's reply")
        return response.copy(content = Content(role = Role.MODEL, parts = listOf(Part(text = trimmed))))
    }

    private fun callTool(response: LlmResponse, name: String) =
        response.copy(content = Content(role = Role.MODEL, parts = listOf(Part(functionCall = FunctionCall(name = name)))))

    // AI PROMPT: Picks the one rule that fits the quiz right now
    private fun tutorRule(invocationId: String): String = when {
        summary.lastInvocationId == invocationId -> TUTOR_AFTER_SUMMARY
        quizOver() -> "$TUTOR_FINISHED\nResults: ${summary.results()}"
        log.pending() != null -> TUTOR_WHEN_WAITING
        log.analyses().size >= QUIZ_LENGTH -> TUTOR_WHEN_DONE
        else -> TUTOR_WHEN_READY + lastResult()
    }

    private fun quizOver() = summary.lastInvocationId != null

    // AI PROMPT: The grader's instruction for the step it is on: judge first, then reply
    private fun graderStep(answer: String): String {
        val pending = log.pending()
        if (pending != null) {
            val check = if (pending.accepts(answer)) "\nCode check: this matches the reference answer, so the verdict is correct." else ""
            return "$GRADER_RULES\nQuestion: ${pending.question}\nReference answer: ${pending.answer}\nStudent's answer: $answer$check"
        }
        val saved = log.lastAnalysis()
        val ending = if (log.analyses().size >= QUIZ_LENGTH) "That was the last one! Say anything to see your results."
        else "Ready for the next question?"
        return "$GRADER_REPLY Start with exactly '${VERDICT_OPENINGS[saved?.verdict]}', " +
            "then explain this tip in your own words: \"${saved?.tip}\", and end with exactly '$ending'. Do not call a tool."
    }

    // AI PROMPT: The last graded answer, so the tutor can explain it if asked
    private fun lastResult(): String {
        val last = log.lastAnalysis() ?: return ""
        return "\nLast result: question \"${last.question}\", verdict ${last.verdict}, tip \"${last.tip}\"."
    }

    private fun text(s: String) = Content(parts = listOf(Part(text = s)))

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
