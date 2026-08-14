from app.services.ai.rag_service import RAGService
from app.services.ai.chat_service import ChatService
from app.services.ai.quiz_service import QuizService
from app.services.ai.flashcard_service import FlashcardService
from app.services.ai.summary_service import SummaryService

class AIService:
    def __init__(self):
        self.rag_service = RAGService()
        self.chat_service = ChatService()
        self.quiz_service = QuizService()
        self.flashcard_service = FlashcardService()
        self.summary_service = SummaryService()

    def generate_response(self, prompt: str, session_id: str = None):
        return self.chat_service.send_message(session_id=session_id, prompt=prompt) if hasattr(self.chat_service, 'send_message') else {"response": "AI processing complete"}

    def ask(self, query: str):
        return self.rag_service.query(query) if hasattr(self.rag_service, 'query') else {"answer": "Answer based on context"}
