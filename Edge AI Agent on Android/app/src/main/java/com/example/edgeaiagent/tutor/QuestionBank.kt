package com.example.edgeaiagent.tutor

// POINT TO LOOK: How many questions make one quiz
const val QUIZ_LENGTH = 5

// FILE INFO: One quiz question with its level (1 easy to 3 hard) and the reference answer
data class Question(val id: Int, val level: Int, val question: String, val answer: String) {
    // GUARDRAIL: Code checks the answer first: an exact match with the reference is always correct.
    // Commas separate alternative answers, unless the answer is a whole sentence
    fun accepts(reply: String): Boolean {
        val options = if (answer.endsWith(".")) listOf(answer) else answer.split(",")
        return options.any { normalize(it) == normalize(reply) }
    }

    private fun normalize(s: String) =
        s.lowercase().replace('’', '\'').replace(Regex("[^a-z' ]"), " ").trim().split(Regex("\\s+")).joinToString(" ")
}

// POINT TO LOOK: The question bank; add questions here, or more alternative answers
val QUESTION_BANK = listOf(
    Question(1, 1, "Fix the sentence: 'She go to school every day.'", "She goes to school every day."),
    Question(2, 1, "Give a synonym for 'happy'.", "glad, joyful, cheerful"),
    Question(3, 1, "Give the opposite of 'cold'.", "hot, warm"),
    Question(4, 1, "Fill the blank: 'I ___ a student.' (am / is / are)", "am"),
    Question(5, 1, "What is the plural of 'child'?", "children"),
    Question(6, 1, "Fix the sentence: 'He have two cats.'", "He has two cats."),
    Question(7, 1, "Fill the blank: 'There ___ three apples on the table.' (is / are)", "are"),
    Question(8, 1, "What is the past tense of 'eat'?", "ate"),
    Question(9, 1, "Give a synonym for 'big'.", "large, huge, giant"),
    Question(10, 1, "Fill the blank: 'She is good ___ math.' (in / at / on)", "at"),
    Question(11, 2, "Fix the sentence: 'I have went to London last year.'", "I went to London last year."),
    Question(12, 2, "Fill the blank: 'If it rains, we ___ stay home.' (will / would)", "will"),
    Question(13, 2, "Give the opposite of 'generous'.", "stingy, mean, selfish"),
    Question(14, 2, "Fix the sentence: 'Me and him went to the park.'", "He and I went to the park."),
    Question(15, 2, "Fill the blank: 'She has lived here ___ 2015.' (for / since)", "since"),
    Question(16, 2, "What is the past participle of 'write'?", "written"),
    Question(17, 2, "Choose the right word: 'Their / There / They're going to the cinema.'", "They're"),
    Question(18, 2, "Give a synonym for 'difficult'.", "hard, tough, challenging"),
    Question(19, 2, "Fix the sentence: 'The informations are useful.'", "The information is useful."),
    Question(20, 2, "Fill the blank: 'He is the ___ student in the class.' (tall / taller / tallest)", "tallest"),
    Question(21, 3, "Fix the sentence: 'If I would have known, I would have helped.'", "If I had known, I would have helped."),
    Question(22, 3, "Give a synonym for 'ubiquitous'.", "everywhere, omnipresent, widespread"),
    Question(23, 3, "Fill the blank: 'Hardly ___ arrived when it began to rain.' (I had / had I)", "had I"),
    Question(24, 3, "Choose the right word: 'The medicine had no effect / affect on him.'", "effect"),
    Question(25, 3, "Fix the sentence: 'Neither the teacher nor the students was ready.'", "Neither the teacher nor the students were ready."),
    Question(26, 3, "Give the opposite of 'meticulous'.", "careless, sloppy"),
    Question(27, 3, "Fill the blank: 'I wish I ___ more time yesterday.' (had / had had)", "had had"),
    Question(28, 3, "Fix the sentence: 'Whom is calling, please?'", "Who is calling, please?"),
    Question(29, 3, "Choose the right word: 'Fewer / Less people came than expected.'", "Fewer"),
    Question(30, 3, "Rewrite in the passive voice: 'The chef cooked the meal.'", "The meal was cooked by the chef."),
)
