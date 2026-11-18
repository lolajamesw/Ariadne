class Stemmer:
    def stem(self, word: str) -> str:
        if word.endswith("ing"):
            return word[:-3]
        return word
