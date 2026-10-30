package com.example.edgeaiagent.tutor

import com.google.adk.kt.tools.BaseTool
import com.google.adk.kt.tools.ToolContext
import com.google.adk.kt.types.FunctionDeclaration
import com.google.adk.kt.types.Schema
import com.google.adk.kt.types.Type

// AI TOOL: The tutor's own tool. Code works out the score, the model only writes the brief
class PerformanceSummaryTool(private val log: TutorLog) :
    BaseTool(name = "performance_summary", description = "Get the student's overall quiz results") {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(type = Type.OBJECT, properties = emptyMap()),
    )

    // POINT TO LOOK: Which turn the summary last ran in; once set, the quiz is over
    @Volatile var lastInvocationId: String? = null
        private set

    override suspend fun run(context: ToolContext, args: Map<String, Any?>): Any {
        lastInvocationId = context.invocationId
        return results()
    }

    fun results(): Map<String, Any> {
        val all = log.analyses()
        val correct = all.count { it.verdict == "correct" }
        val partly = all.count { it.verdict == "partly" }
        val score = if (all.isEmpty()) 0 else ((correct + partly * 0.5) * 100 / all.size).toInt()
        return mapOf(
            "answered" to all.size,
            "correct" to correct,
            "partly" to partly,
            "wrong" to all.count { it.verdict == "wrong" },
            "score_percent" to score,
            "highest_level" to (all.maxOfOrNull { it.level } ?: 0),
            // GUARDRAIL: Right and wrong answers are kept apart, so the brief never calls a right answer weak
            "answered_right" to all.filter { it.verdict == "correct" }.map { it.question },
            "to_practise" to all.filter { it.verdict != "correct" }.map { it.tip },
        )
    }
}
