"""Trie-based dictionary prefix matcher for language detection.

Uses top common words for each language to check if the current
keystroke buffer forms a prefix of a known word.
"""

from __future__ import annotations


class TrieNode:
    __slots__ = ("children", "is_word")

    def __init__(self):
        self.children: dict[str, TrieNode] = {}
        self.is_word: bool = False


class Trie:
    """Prefix trie for fast word/prefix lookup."""

    def __init__(self):
        self._root = TrieNode()
        self._size = 0

    def insert(self, word: str) -> None:
        node = self._root
        for ch in word.lower():
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        if not node.is_word:
            node.is_word = True
            self._size += 1

    def has_prefix(self, prefix: str) -> bool:
        """Check if any word in the trie starts with this prefix."""
        node = self._root
        for ch in prefix.lower():
            if ch not in node.children:
                return False
            node = node.children[ch]
        return True

    def is_word(self, word: str) -> bool:
        """Check if exact word exists in the trie."""
        node = self._root
        for ch in word.lower():
            if ch not in node.children:
                return False
            node = node.children[ch]
        return node.is_word

    def __len__(self) -> int:
        return self._size


# Common words for each language (top ~200 most frequent).
# These are loaded into tries at module init time.

_WORDS_EN = [
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "no", "just", "him", "know", "take",
    "people", "into", "year", "your", "good", "some", "could", "them", "see", "other",
    "than", "then", "now", "look", "only", "come", "its", "over", "think", "also",
    "back", "after", "use", "two", "how", "our", "work", "first", "well", "way",
    "even", "new", "want", "because", "any", "these", "give", "day", "most", "us",
    "is", "are", "was", "were", "been", "being", "has", "had", "did", "does",
    "should", "must", "may", "might", "shall", "need", "let", "help", "try", "start",
    "while", "where", "here", "still", "right", "very", "much", "each", "between", "same",
    "under", "last", "never", "before", "through", "world", "too", "life", "long", "great",
    "little", "own", "old", "other", "place", "end", "point", "home", "hand", "part",
    "high", "keep", "left", "found", "live", "head", "put", "set", "open", "run",
    "read", "write", "code", "file", "test", "data", "list", "name", "type", "line",
    "function", "class", "return", "import", "from", "print", "string", "number", "true", "false",
    "null", "error", "value", "key", "command", "server", "config", "system", "user", "search",
]

_WORDS_RU = [
    "и", "в", "не", "на", "я", "он", "что", "с", "по", "это",
    "она", "но", "его", "все", "так", "как", "мы", "из", "за", "от",
    "же", "ты", "уже", "для", "вот", "был", "да", "нет", "них", "бы",
    "ее", "мне", "мой", "ещё", "бы", "при", "без", "до", "под", "над",
    "быть", "было", "были", "будет", "есть", "стал", "когда", "если", "тоже", "себя",
    "свой", "свою", "этот", "этой", "того", "тому", "может", "только", "очень", "такой",
    "более", "через", "после", "перед", "между", "потом", "потому", "сейчас", "теперь", "здесь",
    "время", "место", "жизнь", "дело", "слово", "сторона", "город", "страна", "работа", "день",
    "человек", "люди", "дети", "глаза", "руки", "голова", "дверь", "конец", "начало", "часть",
    "вопрос", "ответ", "новый", "новая", "новое", "новые", "большой", "маленький", "хороший", "плохой",
    "первый", "последний", "другой", "каждый", "должен", "нужно", "можно", "нельзя", "надо", "сразу",
    "опять", "тогда", "снова", "всегда", "никогда", "давно", "хотя", "чтобы", "кроме", "кто",
    "где", "куда", "откуда", "зачем", "почему", "какой", "который", "сколько", "много", "мало",
    "знать", "думать", "говорить", "сказать", "видеть", "смотреть", "хотеть", "мочь", "идти", "стоять",
    "делать", "дать", "взять", "найти", "написать", "понять", "жить", "работать", "любить", "помочь",
    "спасибо", "пожалуйста", "привет", "здравствуйте", "просто", "очень", "ладно", "хорошо", "давай", "ладно",
    "система", "файл", "данные", "ошибка", "код", "программа", "текст", "список", "команда", "процесс",
]

_WORDS_UA = [
    "і", "в", "не", "на", "я", "він", "що", "з", "по", "це",
    "вона", "але", "його", "все", "так", "як", "ми", "із", "за", "від",
    "же", "ти", "вже", "для", "ось", "був", "так", "ні", "їх", "би",
    "її", "мені", "мій", "ще", "б", "при", "без", "до", "під", "над",
    "бути", "було", "були", "буде", "є", "став", "коли", "якщо", "також", "себе",
    "свій", "свою", "цей", "цій", "того", "тому", "може", "тільки", "дуже", "такий",
    "більш", "через", "після", "перед", "між", "потім", "тому", "зараз", "тепер", "тут",
    "час", "місце", "життя", "справа", "слово", "сторона", "місто", "країна", "робота", "день",
    "людина", "люди", "діти", "очі", "руки", "голова", "двері", "кінець", "початок", "частина",
    "питання", "відповідь", "новий", "нова", "нове", "нові", "великий", "маленький", "гарний", "поганий",
    "перший", "останній", "інший", "кожний", "повинен", "потрібно", "можна", "не можна", "треба", "відразу",
    "знову", "тоді", "знову", "завжди", "ніколи", "давно", "хоча", "щоб", "крім", "хто",
    "де", "куди", "звідки", "навіщо", "чому", "який", "котрий", "скільки", "багато", "мало",
    "знати", "думати", "говорити", "сказати", "бачити", "дивитися", "хотіти", "могти", "іти", "стояти",
    "робити", "дати", "взяти", "знайти", "написати", "зрозуміти", "жити", "працювати", "любити", "допомогти",
    "дякую", "будь ласка", "привіт", "здрастуйте", "просто", "дуже", "гаразд", "добре", "давай", "гаразд",
    "система", "файл", "дані", "помилка", "код", "програма", "текст", "список", "команда", "процес",
]


class DictionaryMatcher:
    """Matches text prefixes against word dictionaries for each language."""

    def __init__(self):
        self.tries: dict[str, Trie] = {}
        self._build_tries()

    def _build_tries(self) -> None:
        for lang, words in [("en", _WORDS_EN), ("ru", _WORDS_RU), ("ua", _WORDS_UA)]:
            trie = Trie()
            for word in words:
                trie.insert(word)
            self.tries[lang] = trie

    def score_prefix(self, texts: dict[str, str]) -> dict[str, float]:
        """Score each language's text interpretation as a word prefix.

        Args:
            texts: {"en": "hel", "ru": "рул", "ua": "рул"}

        Returns:
            {"en": 1.0, "ru": 0.0, "ua": 0.0}
            Score is 1.0 if prefix matches a known word, 0.5 if prefix
            of a known word, 0.0 otherwise.
        """
        scores: dict[str, float] = {}
        for lang, text in texts.items():
            text = text.strip().lower()
            # Split on spaces, check last word (the one being typed)
            words = text.split()
            if not words:
                scores[lang] = 0.0
                continue

            last_word = words[-1]
            trie = self.tries.get(lang)
            if trie is None:
                scores[lang] = 0.0
                continue

            if trie.is_word(last_word):
                scores[lang] = 1.0
            elif trie.has_prefix(last_word):
                scores[lang] = 0.5
            else:
                scores[lang] = 0.0

        return scores
