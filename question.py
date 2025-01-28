
import json
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
#This function will recive a question and return a list (consist of string) question having same meaning
stop_words = set(stopwords.words('english'))
def preprocess(text):
        tokens = text.split()
        return ' '.join([word for word in tokens if word.lower() not in stop_words])

def similar_quizz(question):
    with open ('faq.json','r') as data:
        faq = json.load(data)
        preprocess_quizz=[preprocess(statement) for statement in faq]
        preprocess_input=preprocess(question)

        statements=[preprocess_input]+preprocess_quizz
        # Vectorize all the statements using TF-IDF
        vectorizer = TfidfVectorizer()

        # Create the TF-IDF matrix for all statements
        tfidf_matrix = vectorizer.fit_transform(statements)

        # Calculate Cosine Similarity between the input statement and each comparison statement
        cosine_similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])
        threshold = 0.03
        similar_statements = [faq[i] for i in range(len(faq)) if cosine_similarities[0][i] > threshold]
        return similar_statements


