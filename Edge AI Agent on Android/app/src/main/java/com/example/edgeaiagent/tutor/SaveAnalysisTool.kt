package com.example.edgeaiagent.tutor

import com.google.adk.kt.tools.BaseTool
import com.google.adk.kt.tools.ToolContext
import com.google.adk.kt.types.FunctionDeclaration
import com.google.adk.kt.types.Schema
import com.google.adk.kt.types.Type

// AI TOOL: The only three verdicts the model may choose from
private val VERDICTS = listOf("correct", "partly", "wrong")

// AI TOOL: The grader's tool. Saves the verdict and a tip for the waiting question.
// It is the only tool with arguments, which is why it has the most checks
class SaveAnalysisTool(private val log: TutorLog) :
    BaseTool(name = "save_analysis", description = "Save your verdict on the student's answer") {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "verdict" to Schema(type = Type.STRING, description = "how good the answer is", enum = VERDICTS),
                "tip" to Schema(type = Type.STRING, description = "one short tip for the student"),
            ),
            required = listOf("verdict", "tip"),
        ),
    )

    override suspend fun run(context: ToolContext, args: Map<String, Any?>): Any {
        val question = log.pending() ?: return mapOf("error" to "no question is waiting for an answer")
        val modelVerdict = args["verdict"]?.toString()?.trim('"', ' ')?.lowercase()
        // GUARDRAIL: Anything other than the three verdicts is refused and nothing is saved
        if (modelVerdict !in VERDICTS) return mapOf("error" to "verdict must be one of $VERDICTS")
        val studentAnswer = context.state[STUDENT_ANSWER]?.toString().orEmpty()
        // GUARDRAIL: An exact match with the reference answer is correct, whatever the model said
        val verdict = if (question.accepts(studentAnswer)) "correct" else modelVerdict!!
        val tip = args["tip"]?.toString().orEmpty().take(200)

        val num = log.analyses().size + 1
        // AI MEMORY: Save the result and clear the waiting question
        log.appendAnalysis(Analysis(num, question.id, question.level, question.question, verdict, tip))
        log.clearPending()
        return mapOf("saved" to true, "verdict" to verdict, "answered" to num, "of" to QUIZ_LENGTH)
    }
}
