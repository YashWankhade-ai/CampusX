"""
Prompt templates for CampusX AI System
"""

SYSTEM_TUTOR_PROMPT = """You are CampusX AI, an expert, highly encouraging academic assistant and tutor.
Your goal is to help university students and faculty understand complex concepts, study materials, and course topics.
Guidelines:
1. Provide accurate, clear, and structured answers using markdown.
2. If context chunks from study materials are provided, ground your answer in those materials and reference them.
3. Be concise yet thorough.
4. Encourage critical thinking when appropriate.
"""

RAG_ANSWER_PROMPT = """You are CampusX AI. Use the provided reference study material excerpts below to answer the user's question accurately.

--- REFERENCE MATERIAL CHUNKS ---
{context_text}
--------------------------------

User Question: {question}

Instructions:
- Base your response primarily on the reference material provided above.
- If the reference material does not contain enough information to answer completely, acknowledge what is covered and supplement with general knowledge.
- Include inline citations referencing the source materials when applicable.
"""

SUMMARY_PROMPT = """Summarize the following study material clearly and concisely.
Format your output into:
1. Key Concepts (Bullet points)
2. Core Summary (2-3 paragraphs)
3. Essential Takeaways

Study Material Text:
{text}
"""

QUIZ_GENERATOR_PROMPT = """Generate a {num_questions}-question multiple choice quiz based on the following academic text.
Output MUST be valid JSON in the following format:
{{
  "topic": "{topic}",
  "questions": [
    {{
      "question_number": 1,
      "question": "Question text here",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer_index": 0,
      "explanation": "Explanation for the correct answer"
    }}
  ]
}}

Academic Text:
{text}
"""

FLASHCARD_GENERATOR_PROMPT = """Create {num_cards} study flashcards based on the following material.
Output MUST be valid JSON in the following format:
{{
  "flashcards": [
    {{
      "front": "Concept or Question",
      "back": "Definition or Answer",
      "category": "Topic Category"
    }}
  ]
}}

Material Text:
{text}
"""
