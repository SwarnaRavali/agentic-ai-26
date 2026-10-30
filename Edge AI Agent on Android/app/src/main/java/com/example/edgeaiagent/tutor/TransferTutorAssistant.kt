package com.example.edgeaiagent.tutor

import android.content.Context
import android.util.Log
import com.example.edgeaiagent.Assistant
import com.example.edgeaiagent.TAG
import com.example.edgeaiagent.loadEngine
import com.google.adk.kt.agents.Instruction
import com.google.adk.kt.agents.LlmAgent
import com.google.adk.kt.agents.RunConfig
import com.google.adk.kt.litertlm.LiteRtLmModel
import com.google.adk.kt.runners.InMemoryRunner
import com.google.adk.kt.sessions.SessionKey
import com.google.adk.kt.types.Content
import com.google.adk.kt.types.Part
import com.google.adk.kt.types.Role
import com.google.ai.edge.litertlm.Engine
import java.io.File

private const val APP_NAME = "tutor"
private const val USER_ID = "student"
private const val SESSION_ID = "quiz"

// AI PROMPT: One prompt with numbered rules decides who acts
const val TRANSFER_TUTOR_RULES =
    "You are Tutor, a friendly English teacher running a short quiz. " +
        "You never ask or answer quiz questions yourself; your helper agents do that. " +
        "Use the first rule that fits:\n" +
        "1. If performance_summary has just returned: write a short, warm brief of the results " +
        "(score, what went well, one thing to practise) and say goodbye.\n" +
        "2. If the student wants to stop (says stop, quit, enough, I'm done, bye): call performance_summary.\n" +
        "3. If a question is waiting for an answer: transfer to grader.\n" +
        "4. If the quiz is complete: call performance_summary.\n" +
        "5. Otherwise: transfer to quizmaster."

const val TRANSFER_GRADER_RULES =
    "You are the grader. Compare the student's answer with the reference answer; " +
        "small spelling slips are fine. Call save_analysis once with your verdict and one short tip, " +
        "then transfer to quizmaster."

const val TRANSFER_QUIZMASTER_RULES =
    "You are the quizmaster. First call next_question. " +
        "If it returns done, say in one line that the quiz is finished. " +
        "Otherwise, if last_tip is not none, give it in one short line, " +
        "then ask exactly the question it returned, as 'Q<number>: <question>'. Never give the answer."

// FILE INFO: The same tutor built the other ADK way: sub-agents that hand over control.
// Compare with TutorAssistant: here the tutor never gets control back within a turn
class TransferTutorAssistant(private val context: Context) : Assistant {
    private var engine: Engine? = null
    private var model: LiteRtLmModel? = null
    private var runner: InMemoryRunner? = null
    private val reporter = StepReporter()
    private val log = TutorLog(File(context.filesDir, "tutor"))

    override suspend fun start(): String {
        val (eng, backendName) = loadEngine(context)
        val llm = LiteRtLmModel.create(eng)

        // AI AGENT: The grader saves the result, then hands over to the quizmaster
        val grader = LlmAgent(
            name = "grader",
            description = "Grades the student's answer to the waiting question and saves the result",
            model = llm,
            instruction = Instruction { ctx ->
                val q = log.pending()
                val answer = ctx.state[STUDENT_ANSWER] ?: ""
                text("$TRANSFER_GRADER_RULES\nQuestion: ${q?.question}\nReference answer: ${q?.answer}\nStudent's answer: $answer")
            },
            tools = listOf(SaveAnalysisTool(log)),
            disallowTransferToParent = true,
            includeContents = LlmAgent.IncludeContents.NONE,
            maxSteps = 2,
        )

        // AI AGENT: The quizmaster asks the next question; it cannot hand over again
        val quizmaster = LlmAgent(
            name = "quizmaster",
            description = "Asks the student the next quiz question",
            model = llm,
            instruction = Instruction(TRANSFER_QUIZMASTER_RULES),
            tools = listOf(NextQuestionTool(log)),
            disallowTransferToParent = true,
            disallowTransferToPeers = true,
            includeContents = LlmAgent.IncludeContents.NONE,
            maxSteps = 2,
        )

        // AI AGENT: The tutor hands over to a sub-agent with transfer_to_agent
        val tutor = LlmAgent(
            name = "tutor",
            model = llm,
            instruction = Instruction { _ -> text("$TRANSFER_TUTOR_RULES\n\n${quizStatus()}") },
            // POINT TO LOOK: Sub-agents instead of tools: control moves to them
            subAgents = listOf(grader, quizmaster),
            tools = listOf(PerformanceSummaryTool(log)),
            includeContents = LlmAgent.IncludeContents.NONE,
            maxSteps = 2,
        )

        val r = InMemoryRunner(agent = tutor, appName = APP_NAME, plugins = listOf(reporter))
        r.sessionService.createSession(SessionKey(APP_NAME, USER_ID, SESSION_ID))
        log.clear()

        engine = eng
        model = llm
        runner = r
        Log.i(TAG, "Backend in use: $backendName (transfer tutor)")
        return "$backendName · Transfer tutor"
    }

    // AI AGENT METHOD: Runs one turn; the last agent to speak gives the reply
    override suspend fun chat(text: String, onStep: (String) -> Unit): String {
        val r = checkNotNull(runner) { "Model not loaded yet" }
        reporter.reset(onStep)
        onStep("model: thinking…")

        var answer = ""
        r.runAsync(
            userId = USER_ID,
            sessionId = SESSION_ID,
            newMessage = Content.fromText(Role.USER, text),
            stateDelta = mapOf(STUDENT_ANSWER to text),
            runConfig = RunConfig(maxLlmCalls = 6),
        ).collect { event ->
            if (event.isFinalResponse) answer = event.content?.text().orEmpty().ifBlank { answer }
        }
        return answer.ifEmpty { "Sorry, I could not finish that step. Try again?" }
    }

    private fun quizStatus(): String {
        val answered = log.analyses().size
        val waiting = if (log.pending() != null) "yes" else "no"
        val complete = if (answered >= QUIZ_LENGTH) "yes" else "no"
        return "Quiz status: answered $answered of $QUIZ_LENGTH. " +
            "A question is waiting for an answer: $waiting. Quiz complete: $complete."
    }

    private fun text(s: String) = Content(parts = listOf(Part(text = s)))

    override fun close() {
        runner?.close()
        model?.close()
        engine?.close()
        runner = null
        model = null
        engine = null
    }
}
