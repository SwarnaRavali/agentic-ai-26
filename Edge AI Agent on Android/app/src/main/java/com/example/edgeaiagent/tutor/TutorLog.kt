package com.example.edgeaiagent.tutor

import org.json.JSONObject
import java.io.File

// AI MEMORY: One graded answer, as saved in the file
data class Analysis(val num: Int, val id: Int, val level: Int, val question: String, val verdict: String, val tip: String)

// FILE INFO: The quiz's memory, kept in two small files instead of the chat history.
// analysis.jsonl has one line per graded answer, pending.json the question waiting for an answer
class TutorLog(private val dir: File) {
    private val analysisFile = File(dir, "analysis.jsonl")
    private val pendingFile = File(dir, "pending.json")

    // AI MEMORY: Starts a fresh quiz by deleting both files
    fun clear() {
        dir.mkdirs()
        analysisFile.delete()
        pendingFile.delete()
    }

    fun appendAnalysis(a: Analysis) {
        val line = JSONObject()
            .put("num", a.num).put("id", a.id).put("level", a.level)
            .put("question", a.question).put("verdict", a.verdict).put("tip", a.tip)
        analysisFile.appendText(line.toString() + "\n")
    }

    fun analyses(): List<Analysis> {
        if (!analysisFile.exists()) return emptyList()
        return analysisFile.readLines().filter { it.isNotBlank() }.map {
            val o = JSONObject(it)
            Analysis(o.getInt("num"), o.getInt("id"), o.getInt("level"), o.getString("question"), o.getString("verdict"), o.getString("tip"))
        }
    }

    fun lastAnalysis(): Analysis? = analyses().lastOrNull()

    // AI MEMORY: The question waiting for an answer, or null if there is none
    fun pending(): Question? {
        if (!pendingFile.exists()) return null
        val o = JSONObject(pendingFile.readText())
        return Question(o.getInt("id"), o.getInt("level"), o.getString("question"), o.getString("answer"))
    }

    fun setPending(q: Question) {
        val o = JSONObject().put("id", q.id).put("level", q.level).put("question", q.question).put("answer", q.answer)
        pendingFile.writeText(o.toString())
    }

    fun clearPending() {
        pendingFile.delete()
    }
}
