from .tokenizer import Tokenizer
from .stemmer import Stemmer


class Pipeline:
    def __init__(self):
        self.tokenizer = Tokenizer()
        self.stemmer = Stemmer()

    def run(self, text: str) -> list[str]:
        return [self.stemmer.stem(t) for t in self.tokenizer.split(text)]
