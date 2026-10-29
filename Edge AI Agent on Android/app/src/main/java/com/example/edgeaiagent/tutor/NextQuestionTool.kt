package com.example.edgeaiagent.tutor

import com.google.adk.kt.tools.BaseTool
import com.google.adk.kt.tools.ToolContext
import com.google.adk.kt.types.FunctionDeclaration
import com.google.adk.kt.types.Schema
import com.google.adk.kt.types.Type

// AI TOOL: The quizmaster's tool. Code picks the next question, the model only asks it
class NextQuestionTool(private val log: TutorLog) :
    BaseTool(name = "next_question", description = "Get the next quiz question to ask the student") {
    // AI TOOL: No arguments, so the model has nothing to get wrong
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(type = Type.OBJECT, properties = emptyMap()),
    )

    override suspend fun run(context: ToolContext, args: Map<String, Any?>): Any {
        val answered = log.analyses()
        // POINT TO LOOK: The quiz ends after QUIZ_LENGTH answers
        if (answered.size >= QUIZ_LENGTH) return mapOf("done" to true, "answered" to answered.size)

        val last = answered.lastOrNull()
        // GUARDRAIL: A question is still waiting for an answer, so ask it again
        log.pending()?.let { return questionResult(it, answered.size + 1, last, repeated = true) }

        // POINT TO LOOK: Adaptive level: one step easier after a wrong answer, harder after a right one
        val level = when (last?.verdict) {
            null -> 1
            "wrong" -> last.level - 1
            "correct" -> last.level + 1
            else -> last.level
        }.coerceIn(1, 3)

        val askedIds = answered.map { it.id }.toSet()
        val unasked = QUESTION_BANK.filter { it.id !in askedIds }
        val question = unasked.filter { it.level == level }.randomOrNull() ?: unasked.random()
        // AI MEMORY: Remember the question so the grader knows what was asked
        log.setPending(question)
        return questionResult(question, answered.size + 1, last, repeated = false)
    }

    private fun questionResult(q: Question, number: Int, last: Analysis?, repeated: Boolean) = mapOf(
        "number" to number,
        "level" to q.level,
        "question" to q.question,
        "repeated" to repeated,
        "last_verdict" to (last?.verdict ?: "none"),
        "last_tip" to (last?.tip ?: "none"),
    )
}
