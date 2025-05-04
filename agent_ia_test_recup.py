import json
import re
import aiohttp
import asyncio
import bs4
import ollama
from fuzzywuzzy import fuzz
import os
from bs4 import BeautifulSoup
import random
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

# Assurer que ces fonctions sont définies
def save_data_to_file(data, filename="questions_responses.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Données sauvegardées dans {filename}")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des données: {e}")


def load_cached_data(filename="cached_pages.json"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"Fichier de cache chargé. {len(data)} pages en mémoire.")
            return data
    except FileNotFoundError:
        print(f"Fichier {filename} non trouvé. Création d'un nouveau cache.")
        return {}
    except json.JSONDecodeError:
        print(f"Erreur de décodage de {filename}. Le fichier est peut-être corrompu.")
        import shutil
        shutil.copy(filename, f"{filename}.bak")
        return {}
    except Exception as e:
        print(f"Erreur lors du chargement du cache: {e}")
        return {}

def save_cached_data(cached_data, filename="cached_pages.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            # Convertir les valeurs qui ne sont pas des chaînes en chaînes
            serializable_cache = {}
            for key, value in cached_data.items():
                if isinstance(value, dict):
                    serializable_cache[key] = json.dumps(value, ensure_ascii=False)
                else:
                    serializable_cache[key] = str(value)
            json.dump(serializable_cache, f, ensure_ascii=False, indent=2)
            print(f"Cache sauvegardé dans {filename}")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du cache: {e}")


def extract_phone_number(text):
    # Version améliorée pour capter plus de formats de téléphone
    phone_regex = r"(?:(?:(?:\+|00)33[ ]?(?:\(0\)[ ]?)?)|0)[ ]?[1-9](?:[ .-]?\d{2}){4}"
    matches = re.findall(phone_regex, text)
    if matches:
        return matches[0]

    # Format secondaire, plus général
    basic_regex = r"(?:0\d[ .-]?\d{2}[ .-]?\d{2}[ .-]?\d{2}[ .-]?\d{2})"
    basic_matches = re.findall(basic_regex, text)
    if basic_matches:
        return basic_matches[0]

    return None

def extract_email(text):
    email_regex = r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
    match = re.search(email_regex, text)
    if match:
        return match.group(0)
    return None


def get_contact_info_from_text(text, is_association_question=False):
    phone_number = extract_phone_number(text)
    email = extract_email(text)

    contact_info = None
    if phone_number or email:
        contact_info = "Informations de contact : "
        if phone_number:
            contact_info += f"Téléphone : {phone_number} "
        if email:
            contact_info += f"Email : {email}"
    return contact_info  # Retourner l'information au lieu de None

batiments_universite = {
    "Remond": {"lettre": "A", "ufr": "UFR de Science Politique", "localisation": "ouest, nord ouest"},
    "Grappin": {"lettre": "B", "ufr": "UFR de Philosophie", "localisation": "ouest"},
    "Zazzo": {"lettre": "C", "ufr": "UFR de Psychologie", "localisation": "ouest"},
    "Lefebvre": {"lettre": "D", "ufr": "UFR de Sociologie", "localisation": "ouest",
                 "ufr": "Sciences Sociales et Administration"},
    "Ramnoux": {"lettre": "E", "ufr": "UFR de Littérature Comparée", "localisation": "ouest"},
    "Veil": {"lettre": "F", "localisation": "sud", "ufr": "Droit et Science Politique"},  # UFR non précisée
    "Allais": {"lettre": "G", "localisation": "sud",
               "ufr": "Sciences Economiques Gestion Mathématiques et Informatiques"},  # UFR non précisée
    "Omnisport": {"lettre": "H", "localisation": "sud"},  # Centre sportif
    "Éphémère 1": {"lettre": "M",
                   "ufr": "Direction des affaires logistique et optimisation des environnements du travail",
                   "localisation": "sud"},  # Temporaire, sans UFR précise
    "Maison de l'Étudiant": {"lettre": "MDE", "localisation": "centre, sud ouest"},
    "Ricoeur": {"lettre": "L", "localisation": "est",
                "ufr": "Philosophie Information-Communication Langage Littérature Arts du Spectacle"},
    # UFR non précisée
    "Gymnase": {"lettre": "I"},  # Sport
    "Maier": {"lettre": "V", "localisation": "nord", "ufr": "Langues et Cultures Etrangères"},  # UFR non précisée
    "Milliat": {"lettre": "S", "ufr": "Sciences Techniques des Activités Physiques et sportives",
                "localisation": "Nord"},  # UFR non précisée
    "Éphémère 2": {"lettre": "N", "localisation": "nord"},  # Temporaire
    "BU": {"lettre": "BU", "localisation": "est"},  # Bibliothèque universitaire
    "Restaurant Universitaire": {"lettre": "RU", "localisation": " ouest"},  # Resto U
    "Delbo": {"lettre": "BSL", "ufr": "UFR Lettres, Langues, Arts", "localisation": "sud"},
    "Ginouvès (MAE)": {"lettre": "MAE", "ufr": "Maison Archéologie & Ethnologie"},  # Maison Archéologie & Ethnologie
    "Weber": {"lettre": "W", "localisation": "nord", "ufr": "Salle d'Amphithéâtre"},  # Bâtiment inter-UFR
    "Rouch": {"lettre": "DD"},  # Double lettre, UFR non précisée
    "Formation Continue": {"lettre": "FC", "localisation": "sud"},  # Pour adultes/pros
    "Centre Sportif": {"lettre": "CS", "localisation": "centre"}  # Centre sport global
}

def get_relevant_urls(urls, question, max_urls=5):
    keywords = extract_keywords(question.lower())
    question_lower = question.lower()

    url_categories = {
        "sport": [url for url in urls.keys() if
                  ("suaps" in url.lower() or "sport" in url.lower()) and "mobilites" not in url.lower()],
        "association": [url for url in urls.keys() if "aca2" in url.lower() or "associations" in url.lower()],
        "logement": [url for url in urls.keys() if
                     "logement" in url.lower() or ("crous" in url.lower() and "residence" in url.lower())],
        "bourse": [url for url in urls.keys() if "bourse" in url.lower() or "aide" in url.lower()],
        "general": [url for url in urls.keys() if "contacts" in url.lower() or "accueil" in url.lower()],
        "vie_etudiante": [url for url in urls.keys() if
                          "solidarite" in url.lower() or "entraide" in url.lower() or "soutien" in url.lower()],
        "restauration": [url for url in urls.keys() if
                         any(term in url.lower() for term in ["resto", "restaurant", "cafeteria", "repas"])],
        "handicap": [url for url in urls.keys() if
                     any(term in url.lower() for term in ["handicap", "sha", "accessibilite"])],
        "transport": [url for url in urls.keys() if
                      any(term in url.lower() for term in ["transport", "mobilite", "imagine"])]
    }

    category_scores = {
        "sport": sum(1 for kw in keywords if kw in ["sport", "suaps", "activite", "physique"]),
        "restauration": sum(1 for kw in keywords if
                            kw in ["restauration", "cafeteria", "manger", "repas", "resto", "restaurant", "ru"]),
        "vie_etudiante": sum(1 for kw in keywords if kw in ["service", "vie etudiante", "suio", "aide"]),
        "handicap": sum(1 for kw in keywords if kw in ["handicap", "accessibilite", "sha"]),
        "transport": sum(1 for kw in keywords if kw in ["transport", "navigo", "imagine-r", "mobilite", "bus"]),
        "association": sum(1 for kw in keywords if kw in ["association", "club", "etudiant"]),
        "logement": sum(1 for kw in keywords if kw in ["logement", "residence", "habiter"]),
        "bourse": sum(1 for kw in keywords if kw in ["bourse", "aide", "finance"]),
        "general": 1
    }

    main_category = max(category_scores, key=category_scores.get)
    selected_urls = url_categories.get(main_category, [])[:max_urls - 2] + url_categories["general"][:2]

    if len(selected_urls) < max_urls - 2:
        selected_urls += url_categories["general"][:max_urls - len(selected_urls)]
    else:
        selected_urls += url_categories["general"][:2]

    return selected_urls[:max_urls]

def extract_keywords(question):
    stopwords = {"le", "la", "les", "un", "une", "des", "et", "ou", "de", "du", "au", "aux", "a", "à", "est", "sont",
                 "pour", "dans", "par", "avec", "ce", "cette", "ces", "il", "elle", "ils", "elles", "je", "tu", "nous",
                 "vous"}

    words = re.findall(r'\b\w+\b', question.lower())
    keywords = [word for word in words if word not in stopwords and len(word) > 2]

    question_lower = question.lower()

    if "téléphone" in question_lower or "phone" in question_lower or "contact" in question_lower:
        keywords.append("contact")
    if "email" in question_lower or "mail" in question_lower or "courriel" in question_lower:
        keywords.append("email")
    if "handicap" in question_lower or "accessibilité" in question_lower:
        keywords.append("handicap")
    if "bâtiment" in question_lower or "batiment" in question_lower:
        keywords.append("batiment")


    return list(set(keywords))


sport_categories = {
    "arts_du_mouvement": ["danse", "bachata", "salsa", "tango", "hip-hop", "zumba", "kizomba", "rock", "orientale",
                          "africaine", "contemporaine", "chorégraphie", "cirque"],
    "sports_collectifs": ["football", "basket", "handball", "rugby", "volley", "tchoukball", "kabadji", "futsal"],
    "sports_individuels": ["athlétisme", "escalade", "tir à l'arc", "course"],
    "sports_de_raquette": ["tennis", "badminton", "raquette", "ping-pong", "tennis de table"],
    "sports_de_combat": ["boxe", "judo", "jiu-jitsu", "mma", "grappling", "self-defense", "combat", "art martial"],
    "activités_nautiques": ["natation", "piscine", "nager", "aquagym", "aquabike", "plongée", "baignade", "bnssa"],
    "remise_en_forme": ["fitness", "musculation", "cardio", "renforcement", "posture", "éducation corporelle"],
    "activités_détente": ["yoga", "taichi", "qi gong", "relaxation", "détente", "méditation"]
}


async def process_query(question, data, urls, cached_data):
    is_informal, response = detect_informal_conversation(question)
    if is_informal:
        return response

    # Vérifier si c'est une question générale sur le sport
    sport_response = answer_sport_question(question)
    if sport_response:
        return sport_response

    # Le reste de la fonction reste inchangé
    similar_answer = find_similar_question(data, question)
    if similar_answer:
        return similar_answer

    return await find_info_for_question(question, data, urls, cached_data)

def answer_building_question(question):
    """Répond aux questions concernant les bâtiments de l'université"""
    import time
    import random

    # Simuler un délai de traitement (environ 3 secondes)
    time.sleep(random.uniform(2.8, 3.2))

    question_lower = question.lower()

    # Cas 1: Question sur un bâtiment spécifique par son nom
    for batiment, info in batiments_universite.items():
        if batiment.lower() in question_lower:
            reponse = f"Le bâtiment {batiment} (lettre {info['lettre']}) "
            if "ufr" in info:
                reponse += f"abrite {info['ufr']} "
            if "localisation" in info:
                reponse += f"et se trouve dans la partie {info['localisation']} du campus."
            else:
                reponse += "se trouve sur le campus de l'université Paris Nanterre."
            return reponse

    # Cas 2: Question sur une UFR spécifique
    for batiment, info in batiments_universite.items():
        if "ufr" in info:
            ufr_lower = info["ufr"].lower()
            if any(keyword in ufr_lower for keyword in ["philo", "philosophie"]) and "philo" in question_lower:
                return f"L'UFR de Philosophie se trouve dans le bâtiment {batiment} (lettre {info['lettre']}), situé dans la partie {info.get('localisation', 'ouest')} du campus."
            elif any(keyword in ufr_lower for keyword in ["socio", "sociologie"]) and "socio" in question_lower:
                return f"L'UFR de Sociologie se trouve dans le bâtiment {batiment} (lettre {info['lettre']}), situé dans la partie {info.get('localisation', 'ouest')} du campus."
            elif any(keyword in ufr_lower for keyword in ["psycho", "psychologie"]) and "psycho" in question_lower:
                return f"L'UFR de Psychologie se trouve dans le bâtiment {batiment} (lettre {info['lettre']}), situé dans la partie {info.get('localisation', 'ouest')} du campus."
            elif "politique" in ufr_lower and "politique" in question_lower:
                return f"L'UFR de Science Politique se trouve dans le bâtiment {batiment} (lettre {info['lettre']}), situé dans la partie {info.get('localisation', 'ouest')} du campus."
            elif "lettres" in ufr_lower and "lettres" in question_lower:
                return f"L'UFR Lettres, Langues, Arts se trouve dans le bâtiment {batiment} (lettre {info['lettre']})."
            elif "segmi" in question_lower or (
                    "économie" in question_lower or "economie" in question_lower or "gestion" in question_lower):
                # SEGMI n'est pas dans le dictionnaire, mais on peut ajouter une réponse spécifique
                return "L'UFR SEGMI (Sciences Économiques, Gestion, Mathématiques, Informatique) se trouve dans le bâtiment G (Allais), situé dans la partie sud du campus."

    # Cas 3: Question par lettre de bâtiment
    for lettre in ["a", "b", "c", "d", "e", "f", "g", "h", "l", "m", "n", "s", "v", "w"]:
        if f"bâtiment {lettre}" in question_lower or f"batiment {lettre}" in question_lower:
            for batiment, info in batiments_universite.items():
                if info["lettre"].lower() == lettre:
                    reponse = f"Le bâtiment {lettre.upper()} s'appelle {batiment}"
                    if "ufr" in info:
                        reponse += f" et abrite {info['ufr']}"
                    if "localisation" in info:
                        reponse += f". Il est situé dans la partie {info['localisation']} du campus."
                    else:
                        reponse += "."
                    return reponse

    # Cas 4: Question générale sur les bâtiments
    if "batiments" in question_lower or "bâtiments" in question_lower:
        return "Le campus de Paris Nanterre compte de nombreux bâtiments identifiés par des lettres (A à W). Par exemple, le bâtiment A (Remond) abrite l'UFR de Science Politique, le bâtiment G (Allais) se trouve au sud du campus, et la Maison de l'Étudiant (MDE) est située au centre-sud-ouest du campus."
    return None


def get_main_subject(question):
    patterns = [
        r"est.ce qu'il y a des? ([\w\s]+) (à|a|au|aux|dans|en)",
        r"y a.t.il des? ([\w\s]+) (à|a|au|aux|dans|en)",
        r"existe.t.il des? ([\w\s]+) (à|a|au|aux|dans|en)"
    ]

    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return match.group(1).strip()

    keywords = extract_keywords(question)
    important_words = [word for word in keywords if
                       len(word) > 3 and word not in ["asso", "association", "université", "campus"]]

    if important_words:
        return important_words[0]
    return None


def load_data_from_file(filename="questions_responses.json"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"Fichier de cache chargé. {len(data)} questions en mémoire.")
            return data
    except FileNotFoundError:
        print(f"Fichier {filename} non trouvé. Création d'un nouveau cache.")
        return {}
    except json.JSONDecodeError:
        print(f"Erreur de décodage de {filename}. Le fichier est peut-être corrompu.")
        import shutil
        shutil.copy(filename, f"{filename}.bak")
        return {}


def detect_informal_conversation(message):
    """Détecte si le message est une salutation ou conversation informelle"""

    # Convertir en minuscules pour faciliter la détection
    message_lower = message.lower().strip()

    # Détecter les salutations
    salutations = ["salut", "hello", "bonjour", "coucou", "hey", "yo", "bonsoir", "wesh",
                   "slt", "bjr", "cc", "kikou", "hi", "hola"]

    # Détecter les variantes de "ça va"
    ca_va_variants = ["ça va", "ca va", "comment vas-tu", "comment tu vas", "comment va",
                      "la forme", "tu vas bien", "vous allez bien", "comment allez-vous",
                      "comment ça va", "comment ca va", "ça dit quoi", "ca dit quoi"]

    # Détecter les expressions positives
    positive_mood = ["je vais bien", "ça va bien", "ca va bien", "je me sens bien",
                     "super", "génial", "content", "heureux", "trop bien", "bonne journée",
                     "je suis heureux", "je suis content", "je suis joyeux"]

    # Détecter les expressions négatives
    negative_mood = ["je vais mal", "ça va pas", "ca va pas", "je me sens mal",
                     "pas bien", "triste", "déprimé", "déprime", "mauvaise journée",
                     "je suis triste", "je suis pas bien", "je suis déprimé"]

    # Réponses pour les salutations
    salutation_responses = [
        "Bonjour ! En quoi puis-je vous aider aujourd'hui ?",
        "Salut ! Comment ça va aujourd'hui ?",
        "Hello ! Comment vous sentez-vous aujourd'hui ?",
        "Coucou ! Que puis-je faire pour vous aider ?",
        "Hey ! Tout ce passe bien de votre côté ?"
    ]

    # Réponses positives
    positive_responses = [
        "C'est super de l'entendre ! En quoi puis-je vous aider aujourd'hui ?",
        "Je suis content pour vous ! Comment puis-je vous être utile ?",
        "Excellente nouvelle ! N'hésitez pas à me poser vos questions sur l'université.",
        "Ça fait plaisir ! Que puis-je faire pour vous aujourd'hui ?"
    ]

    # Réponses de réconfort
    comfort_responses = [
        "Je suis désolé de l'entendre. N'hésitez pas à me poser des questions sur l'université, je suis là pour vous aider du mieux que je peux.",
        "Courage, les choses vont s'améliorer. En attendant, je suis là pour répondre à vos questions sur l'université.",
        "Je comprends que ce n'est pas facile. N'hésitez pas à me demander des informations qui pourraient vous être utiles.",
        "Prenez soin de vous. Si vous avez besoin d'informations sur les services d'aide psychologique de l'université, je peux vous renseigner."
    ]

    # Réponses aux "ça va"
    ca_va_responses = [
        "Je vais bien, merci ! Je suis là pour répondre à vos questions sur l'université. Comment puis-je vous aider ?",
        "Tout va bien, merci de demander ! En quoi puis-je vous être utile aujourd'hui ?",
        "Tout roule pour moi, je suis opérationnel et prêt à vous aider. Quelle information recherchez-vous ?",
        "Oui, Je suis toujours prêt à aider ! Que souhaitez-vous savoir sur l'université ?"
    ]

    is_just_greeting = any(greeting in message_lower for greeting in salutations) and len(message_lower.split()) <= 3
    is_ca_va = any(variant in message_lower for variant in ca_va_variants)
    is_positive = any(pos in message_lower for pos in positive_mood)
    is_negative = any(neg in message_lower for neg in negative_mood)
    if is_just_greeting:
        return True, random.choice(salutation_responses)
    elif is_ca_va:
        return True, random.choice(ca_va_responses)
    elif is_positive:
        return True, random.choice(positive_responses)
    elif is_negative:
        return True, random.choice(comfort_responses)

    return False, None

def answer_university_contact_question(question):
    """Répond aux questions concernant l'université avec les informations prédéfinies"""
    question_lower = question.lower()

    university_info = {
        "nom": "Université Paris Nanterre",
        "adresse": "200 avenue de la République, 92001 Nanterre Cedex",
        "telephone": "01 40 97 72 00",
        "site_web": "https://www.parisnanterre.fr/",
        "rer": "Prendre la ligne A du R.E.R., direction Saint-Germain-en-Laye, et descendre à la station « Nanterre Université ».",
        "train": "Prendre le train Ligne L à la gare Saint-Lazare, direction « Nanterre université » ou « Cergy-le-haut », et descendre à la station « Nanterre Université ».",
        "bus": "– ligne 259 « Nanterre-Anatole France – Saint-Germain-en-Laye RER »\n– ligne 304 « Nanterre Place de la Boule – Asnières-Gennevilliers Les Courtilles » : arrêt Nanterre Université\n– ligne 367 « Rueil-Malmaison RER – Pont de Bezons » : arrêt Université Paris Nanterre Université RER\n– ligne 378 « Nanterre-Ville RER – Asnières-Gennevilliers Les Courtilles » : arrêt Nanterre Université",
        "route": "L'université est accessible par les autoroutes A86 et A14. Des possibilités de stationnement gratuit sont disponibles autour du campus.",
        "temps": "Les différents moyens de transports placent le campus de Nanterre à 5 minutes du quartier de la Défense, à 10 minutes de la place Charles de Gaulle-Etoile et à 20 minutes du quartier latin.",
        "velo": "Par l'entrée Noël Pons et par l'entrée avenue de la république. Des arceaux pour accrocher votre vélo sont situés a proximité des entrées de plusieurs bâtiments. Une station Véligo est localisée sur le parvis de l'université. Elle est accessible avec un passe Navigo et équipée de bornes de recharge pour les vélos à assistance électrique."
    }

    # Vérification si la question concerne spécifiquement l'université et une demande d'info précise
    university_terms = ["université", "paris nanterre", "univ", "fac", "campus"]
    university_mentioned = any(term in question_lower for term in university_terms)

    if not university_mentioned:
        return None

    # Vérifier si c'est une demande d'information spécifique
    is_specific_request = False

    # Question sur l'adresse
    if any(term in question_lower for term in ["adresse", "où se trouve", "où est", "localisation", "situé", "située"]):
        is_specific_request = True
        return f"{university_info['nom']}\n{university_info['adresse']}"

    # Question sur le téléphone ou contact
    elif any(term in question_lower for term in ["téléphone", "numéro", "contact", "appeler", "joindre"]):
        is_specific_request = True
        return f"{university_info['nom']}\nStandard : {university_info['telephone']}"

    # Question sur le site web
    elif any(term in question_lower for term in ["site", "site web", "site internet", "page web", "internet"]):
        is_specific_request = True
        return f"Le site web officiel de {university_info['nom']} est : {university_info['site_web']}"

    # Question sur les moyens de transport
    elif any(term in question_lower for term in
             ["rer", "r.e.r", "train", "sncf", "bus", "autobus", "voiture", "route", "vélo", "velo", "bicyclette",
              "veligo", "transport", "venir", "accès", "acces", "arriver", "autoroute", "aller", "comment s'y rendre"]):
        is_specific_request = True

    if not is_specific_request:
        return None
    # Question générale sur les transports
    elif any(term in question_lower for term in
             ["transport", "venir", "accès", "acces", "arriver", "comment s'y rendre"]):
        response = "Accès à l'Université Paris Nanterre :\n\n"
        response += "En transports en commun :\n"
        response += f"- Par le R.E.R. : {university_info['rer']}\n"
        response += f"- Par le train : {university_info['train']}\n"
        response += f"- Par le bus : {university_info['bus']}\n\n"
        response += f"Par la route : {university_info['route']}\n\n"
        response += f"En vélo : {university_info['velo']}\n\n"
        response += f"{university_info['temps']}"
        return response

    else:
        response = f"{university_info['nom']}\n"
        response += f"Adresse : {university_info['adresse']}\n"
        response += f"Standard : {university_info['telephone']}\n"
        response += f"Site web : {university_info['site_web']}\n\n"
        response += "Pour des informations plus précises sur les moyens d'accès, posez une question spécifique sur les transports."
        return response


def answer_sport_question(question):
    """Répond aux questions générales sur les sports proposés à l'université"""
    question_lower = question.lower()

    # Définir les catégories de sports
    sport_categories = {
        "arts_du_mouvement": ["danse", "bachata", "salsa", "tango", "hip-hop", "zumba", "kizomba", "rock", "orientale",
                              "africaine", "contemporaine", "chorégraphie", "cirque"],
        "sports_collectifs": ["football", "basket", "handball", "rugby", "volley", "tchoukball", "kabadji", "futsal"],
        "sports_individuels": ["athlétisme", "escalade", "tir à l'arc", "course"],
        "sports_de_raquette": ["tennis", "badminton", "raquette", "ping-pong", "tennis de table"],
        "sports_de_combat": ["boxe", "judo", "jiu-jitsu", "mma", "grappling", "self-defense", "combat", "art martial"],
        "activités_nautiques": ["natation", "piscine", "nager", "aquagym", "aquabike", "plongée", "baignade", "bnssa"],
        "remise_en_forme": ["fitness", "musculation", "cardio", "renforcement", "posture", "éducation corporelle"],
        "activités_détente": ["yoga", "taichi", "qi gong", "relaxation", "détente", "méditation"]
    }

    # Termes de recherche pour identifier les questions générales sur le sport
    general_sport_terms = ["sport", "activité", "sportif", "sportive", "suaps", "activités physiques",
                           "quels sports", "offre sportive", "pratiquer", "faire du sport"]

    # Vérifier si c'est une question générale sur les sports
    is_general_sport_question = any(term in question_lower for term in general_sport_terms) and not any(
        sport in question_lower for category in sport_categories.values() for sport in category)

    if is_general_sport_question:
        response = "L'université Paris Nanterre propose une grande variété d'activités sportives organisées par le SUAPS (Service Universitaire des Activités Physiques et Sportives). Voici les principales catégories de sports disponibles :\n\n"

        for category, sports in sport_categories.items():
            formatted_category = category.replace('_', ' ').title()
            response += f"**{formatted_category}** : {', '.join(sports[:5])}..."
            if len(sports) > 5:
                response += f" et {len(sports) - 5} autres"
            response += "\n"

        response += "\nPour des informations plus précises sur les horaires, lieux et modalités d'inscription, vous pouvez consulter le site du SUAPS : https://suaps.parisnanterre.fr\n\n"
        response += "Si vous êtes intéressé par un sport en particulier, n'hésitez pas à poser une question spécifique (par exemple : 'A quelle heure est le judo a l'université ? ?', 'Y a til du tennis a l'univeristé' ou  'Où se pratique le tennis à l'université ?')."

        return response

    return None

def find_similar_question(existing_data, question):
    normalized_question = question.lower().strip()
    current_keywords = set(extract_keywords(normalized_question))
    best_match = None
    best_score = 0

    # Vérifier d'abord si c'est une question spécifique sur les contacts de l'université
    university_contact_answer = answer_university_contact_question(question)
    if university_contact_answer:
        return university_contact_answer

    # Vérifier si c'est une question sur les bâtiments
    building_answer = answer_building_question(question)
    if building_answer:
        return building_answer

    # Le reste de la fonction reste inchangé
    for saved_question, answer in existing_data.items():
        saved_keywords = set(extract_keywords(saved_question.lower().strip()))
        text_similarity = fuzz.token_sort_ratio(saved_question.lower(), normalized_question)

        keyword_intersection = len(current_keywords.intersection(saved_keywords))
        keyword_union = len(current_keywords.union(saved_keywords))
        keyword_similarity = (keyword_intersection / keyword_union * 100) if keyword_union > 0 else 0
        combined_similarity = (keyword_similarity * 0.7) + (text_similarity * 0.3)

        current_subject = get_main_subject(normalized_question)
        saved_subject = get_main_subject(saved_question.lower())

        if current_subject and saved_subject and current_subject != saved_subject:
            combined_similarity *= 0.5

        if combined_similarity > 75 and combined_similarity > best_score:
            best_score = combined_similarity
            best_match = answer
            print(f"Question potentiellement similaire trouvée: '{saved_question}' (score: {combined_similarity:.1f}%)")

    if best_score > 75:
        return best_match
    return None


def extract_relevant_content(soup, question_keywords):
    relevant_sections = []

    for heading in soup.find_all(['h1', 'h2', 'h3']):
        heading_text = heading.get_text().lower()
        if any(keyword in heading_text for keyword in question_keywords):
            section_content = [heading.get_text()]
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h1', 'h2', 'h3']:
                    break
                if sibling.name in ['p', 'ul', 'ol', 'table']:
                    section_content.append(sibling.get_text())
            relevant_sections.append(" ".join(section_content))

    if not relevant_sections:
        main_content = soup.select_one('#content, main, article, .content')
        if main_content:
            relevant_sections.append(main_content.get_text()[:1500])
        else:
            relevant_sections.append(soup.get_text()[:1000])
    return "\n".join(relevant_sections)


def group_similar_pages_by_content(url_text_dict, threshold=85):
    grouped = []
    visited = set()

    urls = list(url_text_dict.keys())
    for i, url1 in enumerate(urls):
        if url1 in visited:
            continue
        group = [url1]
        visited.add(url1)
        for j in range(i + 1, len(urls)):
            url2 = urls[j]
            if url2 in visited:
                continue
            score = fuzz.ratio(url_text_dict[url1], url_text_dict[url2])
            if score >= threshold:
                group.append(url2)
                visited.add(url2)
        grouped.append(group)
    return grouped


async def get_text_from_url_with_delay(url, cached_data, delay=2, retries=3):

    if url in cached_data:
        return cached_data[url]

    attempt = 0
    while attempt < retries:
        try:
            await asyncio.sleep(delay)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        print(f"Erreur: statut {response.status} pour {url}")
                        attempt += 1
                        continue
                    page = await response.text()

            soup = BeautifulSoup(page, 'html.parser')

            for script in soup(['script', 'style']):
                script.decompose()

            content_texts = []

            for selector in ['#content', 'main', 'article', '.content', '#main-content', '.entry-content']:
                content = soup.select_one(selector)
                if content:
                    # Extraire les titres et paragraphes avec leur hiérarchie
                    for element in content.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'table']):
                        if element.name.startswith('h'):
                            content_texts.append(f"\n## {element.get_text().strip()}")
                        elif element.name == 'p':
                            content_texts.append(element.get_text().strip())
                        elif element.name in ['ul', 'ol']:
                            for li in element.find_all('li'):
                                content_texts.append(f"- {li.get_text().strip()}")
                        elif element.name == 'table':
                            # Extraction simplifiée des tableaux
                            content_texts.append("Tableau trouvé avec les informations suivantes:")
                            for tr in element.find_all('tr'):
                                row_text = ' | '.join([td.get_text().strip() for td in tr.find_all(['td', 'th'])])
                                content_texts.append(f"  {row_text}")
                    break  # Utiliser le premier sélecteur qui fonctionne

            # Si aucun contenu structuré n'a été trouvé, utiliser le texte brut
            if not content_texts:
                content_texts = [soup.get_text(separator=' ')]

            text = '\n'.join(content_texts)

            # Nettoyer le texte pour supprimer les espaces multiples
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\n\s*\n', '\n\n', text)

            cached_data[url] = text
            save_cached_data(cached_data)
            return text
        except Exception as e:
            print(f"Erreur lors de la récupération de {url} (tentative {attempt + 1}): {e}")
            attempt += 1
            delay = random.uniform(3, 5)
            if attempt == retries:
                print(f"Échec de la récupération de {url} après {retries} tentatives.")
                return ""

def extract_specific_information(soup, question_keywords):
    """Extrait des informations spécifiques basées sur les mots-clés de la question"""
    relevant_info = []

    for keyword in question_keywords:
        # 1. Chercher dans les titres et contenus adjacents
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            if keyword.lower() in heading.get_text().lower():
                section = [f"SECTION: {heading.get_text()}"]
                current = heading.next_sibling
                # Collecter les paragraphes suivant le titre jusqu'au prochain titre
                while current and current.name not in ['h1', 'h2', 'h3', 'h4']:
                    if current.name in ['p', 'ul', 'ol', 'div'] and current.get_text().strip():
                        section.append(current.get_text().strip())
                    current = current.next_sibling
                relevant_info.append('\n'.join(section))

        # 2. Chercher dans les paragraphes
        for para in soup.find_all(['p', 'li']):
            text = para.get_text().lower()
            if keyword.lower() in text:
                relevant_info.append(f"INFORMATION: {para.get_text().strip()}")

        # 3. Chercher dans les tableaux pour les informations structurées
        for table in soup.find_all('table'):
            table_has_keyword = False
            for cell in table.find_all(['th', 'td']):
                if keyword.lower() in cell.get_text().lower():
                    table_has_keyword = True
                    break

            if table_has_keyword:
                table_data = ["TABLE:"]
                for row in table.find_all('tr'):
                    cells = row.find_all(['th', 'td'])
                    if cells:
                        row_text = ' | '.join(cell.get_text().strip() for cell in cells)
                        table_data.append(row_text)
                relevant_info.append('\n'.join(table_data))

    # Si des informations spécifiques sont trouvées, les retourner
    if relevant_info:
        return '\n\n'.join(relevant_info)
    return None


async def get_multiple_texts(urls, cached_data):
    tasks = []
    for url in urls:
        if url in cached_data:
            continue
        tasks.append(get_text_from_url_with_delay(url, cached_data))
    if tasks:
        await asyncio.gather(*tasks)
    return [cached_data.get(url, "") for url in urls]


def ask_ollama_improved(context, question):
    """
    Version améliorée avec un meilleur traitement pour les questions sportives
    """
    question_lower = question.lower()
    is_sport_question = any(term in question_lower for term in [
        "sport", "suaps", "activité physique", "sportive", "judo", "danse",
        "football", "natation", "piscine", "basket", "handball", "volley", "tennis",
        "musculation", "yoga", "boxe", "escalade", "fitness", "ju jitsu",
        "ping pong", "tennis de table", "badminton", "cardio"
    ])

    # Autres vérifications de type de question (inchangées)
    is_association_question = any(
        term in question_lower for term in ["association", "club", "asso", "activité étudiante", "existe-t-il"])
    is_student_life_question = any(term in question_lower for term in
                                   ["aide", "soutien", "entraide", "vie étudiante", "solidarité", "accompagnement"])
    is_crous_question = any(
        term in question_lower for term in ["crous", "resto", "restaurant", "cafétéria", "restauration", "repas"])
    is_transport_question = any(
        term in question_lower for term in ["transport", "bus", "métro", "imagine r", "train", "rer", "navigo"])
    is_handicap_question = any(
        term in question_lower for term in ["handicap", "sha", "accessibilité", "situation de handicap"])

    system_prompt = """Tu es un assistant universitaire précis qui répond de manière COMPLÈTE et DÉTAILLÉE."""


    if is_crous_question:
        system_prompt += """
        INSTRUCTION CRITIQUE: Cette question concerne le CROUS de Versailles.

        Tu dois:
        1. Toujours préciser qu'il s'agit du CROUS de Versailles
        2. Fournir les coordonnées exactes (numéro de téléphone, email, site) si elles sont présentes dans les données
        3. Indiquer les différents moyens de contacter le CROUS de Versailles
        4. Ne pas confondre avec d'autres CROUS régionaux

        Le numéro de téléphone du CROUS de Versailles est le 09 72 59 65 65 et son site web : www.crous-versailles.fr
        """

    if is_association_question and not is_crous_question:
        system_prompt += """
        INSTRUCTION CRITIQUE: Cette question concerne UNIQUEMENT les associations étudiantes de l'université.

        NE MENTIONNE PAS LE CROUS DE VERSAILLES dans ta réponse sauf s'il y a une relation directe et explicite.

        Tu dois:
        1. Lister plusieurs associations dans différents domaines
        2. Présenter leurs activités principales
        3. Indiquer leurs contacts si disponibles
        4. Mentionner le site des associations: https://ufr-lce.parisnanterre.fr/associations
        """

    if is_transport_question:
        system_prompt += """
            INSTRUCTION CRITIQUE: Cette question concerne les transports pour les étudiants.

            Tu dois:
            1. Donner des informations sur les cartes Imagine R ou Navigo si pertinent
            2. Préciser les réductions pour étudiants
            3. Mentionner les lignes de transport desservant l'université si connues
            4. Indiquer les démarches à suivre pour obtenir les cartes de transport
            """

    if is_handicap_question:
        system_prompt += """
            INSTRUCTION CRITIQUE: Cette question concerne le Service Handicap et Accessibilité (SHA).

            Tu dois:
            1. Décrire précisément les services offerts par le SHA
            2. Indiquer comment contacter le service (numéro, email, bureau)
            3. Préciser les démarches à effectuer pour bénéficier d'aménagements
            4. Mentionner les horaires d'ouverture si disponibles
            """

    if is_student_life_question:
        system_prompt += """
        INSTRUCTION CRITIQUE: Cette question concerne UNIQUEMENT les associations d'aide à la vie étudiante. 

        Tu dois EXCLUSIVEMENT mentionner les associations qui:
        1. Fournissent une aide directe et concrète aux étudiants (aide financière, logement, alimentaire, psychologique)
        2. Offrent des services de soutien et d'accompagnement (administratif, juridique, santé)
        3. Sont spécialisées dans la solidarité et l'entraide étudiante
        4. Défendent les intérêts des étudiants auprès de l'administration

        IGNORER COMPLÈTEMENT:
        - Les associations culturelles
        - Les associations sportives
        - Les associations académiques/disciplinaires
        - Les associations de filières qui n'ont pas d'actions concrètes d'aide aux étudiants

        Pour chaque association pertinente, précise:
        - Son nom complet
        - Ses services concrets d'aide aux étudiants
        - Comment la contacter
        """
    else:
        system_prompt += """
        IMPORTANT: Identifie d'abord la catégorie exacte de la question (sport, association, logement, bourse, restauration, transport ,etc.).
        Quand il s'agit de sports ou d'associations, donne des informations exhaustives incluant les horaires, lieux, contacts, site internet et modalités d'inscription si disponibles.
        """

    system_prompt += """
    Réponds uniquement en fonction des informations fournies, mais assure-toi que ta réponse soit la plus complète possible.
    Structure ta réponse de manière claire avec des points clés si nécessaire.
    N'extrais pas seulement les contacts - ils doivent compléter l'information, pas la remplacer.
    Si l'information n'est pas complète dans les données, précise quelles informations manquent.
    """


    urls_in_context = []
    for line in context.split('\n'):
        if line.startswith("Source: "):
            urls_in_context.append(line.replace("Source: ", "").strip())

    most_relevant_url = ""
    if urls_in_context:
        most_relevant_url = urls_in_context[0]

    system_prompt += """
        CRITIQUE: Ta mission est d'EXTRAIRE et de SYNTHÉTISER l'information pertinente pour la question posée.

        1. Identifie les passages clés dans les données fournies qui répondent directement à la question
        2. Fais une synthèse précise et complète des informations pertinentes
        3. Structure ta réponse de manière claire (titres, points clés, listes si nécessaire)
        4. INCLUS ABSOLUMENT les informations de contact si elles sont présentes (téléphone, email, site web)
        5. Si plusieurs sources contiennent des informations pertinentes, combine-les dans une réponse cohérente

        TA RÉPONSE DOIT ÊTRE UTILE ET ACTIONNABLE - l'utilisateur doit pouvoir agir sur base de ta réponse.
        """

    full_context = f"""Voici les informations trouvées sur les sites web:
    {context}

    QUESTION: {question}

    Ta tâche est d'extraire uniquement les informations pertinentes pour répondre à cette question de la manière la plus précise et complète possible.
    """

    full_context = f"""Voici les informations trouvées sur les sites web:
        {context}

        QUESTION: {question}

        Ta tâche est d'extraire uniquement les informations pertinentes pour répondre à cette question de la manière la plus précise et complète possible.
        """

    response = ollama.chat(
        model="mistral",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_context}
        ]
    )

    content = response['message']['content']



    if is_association_question or "association" in question_lower or any(
                x in content.lower() for x in ["association", "aca2", "club étudiant"]):
            if not content.endswith('.'):
                content += '.'

            content += "\n\nPour plus d'informations sur toutes les associations de l'université, consultez: https://ufr-lce.parisnanterre.fr/associations"


    if not any(url in content for url in urls_in_context):
        content += f"\n\nPour plus d'informations, consultez: {most_relevant_url}"

    source_url = None
    for url in urls_in_context:
        if url in content:
            source_url = url
            break

    if not source_url and urls_in_context:
        source_url = urls_in_context[0]
        content += f"\n\nSource: {source_url}"

    # S'assurer que la source est toujours à la fin
    if source_url and not content.endswith(source_url):
        # Supprimer toute mention précédente de l'URL source
        content = re.sub(f"Source: {re.escape(source_url)}", "", content)
        # Ajouter l'URL source à la fin
        content += f"\n\nSource: {source_url}"

    return content
async def find_info_for_question(question, data, urls, cached_data):
    """
    Version améliorée qui dirige toujours vers le site SUAPS pour les questions sportives
    et inclut systématiquement les horaires et jours
    """
    # Vérifier d'abord si c'est une question sur le sport
    sport_response = answer_sport_question(question)
    if sport_response:
        # Pour les questions sportives, ajouter systématiquement la source correcte
        sport_response += "\n\nSource: https://suaps.parisnanterre.fr"
        return sport_response

    # Si ce n'est pas une question sur le sport, continuer avec le traitement normal
    similar_answer = find_similar_question(data, question)
    if similar_answer:
        return similar_answer

    # Le reste de la fonction reste inchangé
    keywords = extract_keywords(question.lower())

    if isinstance(urls, dict):
        relevant_urls = []
        question_lower = question.lower()

        categories = {
            "crous": ["crous", "resto", "restaurant", "cafet", "repas"],
            "association": ["association", "club", "aca2", "étudiant", "activité"],
            "transport": ["transport", "bus", "métro", "train", "rer", "imagine"],
            "handicap": ["handicap", "sha", "accessibilité"],
            "sport": ["sport", "suaps", "activité physique", "sportive", "danse", "yoga", "football"]
        }

        detected_categories = []
        for category, terms in categories.items():
            if any(term in question_lower for term in terms):
                detected_categories.append(category)

        # Si la catégorie "sport" est détectée, orienter directement vers le site du SUAPS
        if "sport" in detected_categories:
            return answer_sport_question(question) + "\n\nSource: https://suaps.parisnanterre.fr"

        if not detected_categories:
            for url, tags in urls.items():
                if any(keyword in ' '.join(tags).lower() for keyword in keywords):
                    relevant_urls.append(url)
        else:
            for category in detected_categories:
                category_urls = []
                for url, tags in urls.items():
                    if category in ' '.join(tags).lower() or any(
                            term in ' '.join(tags).lower() for term in categories[category]):
                        category_urls.append(url)

                relevant_urls.extend(category_urls[:3])

        # Limiter à 10 URLs au total
        relevant_urls = relevant_urls[:10]
    else:
        # Utiliser la méthode existante si urls est une liste
        relevant_urls = [url for url in urls if any(keyword in url.lower() for keyword in keywords)][:10]

    if not relevant_urls:
        relevant_urls = urls[:10]

    print(f"Recherche dans {len(relevant_urls)} URLs pertinentes...")
    context = ""
    results = []

    for url in relevant_urls:
        try:
            text = await get_text_from_url_with_delay(url, cached_data)
            if text:
                if isinstance(text, dict):
                    text_str = json.dumps(text, ensure_ascii=False, indent=2)
                    context += f"\nSource: {url}\n"
                    context += f"Informations: {text_str[:3000]}...\n\n"
                    results.append((url, text_str))
                else:
                    context += f"\nSource: {url}\n"
                    text_content = str(text)[:3000]
                    context += f"Informations: {text_content}...\n\n"
                    results.append((url, text_content))
        except Exception as e:
            print(f"Erreur lors du traitement de l'URL {url}: {e}")

    if not results:
        return "Désolé, je n'ai pas pu extraire d'informations des sites web pertinents pour répondre à votre question."

    context = ""
    for url, text in results:
        context += f"\nSource: {url}\n"
        context += f"Informations: {text}...\n\n"

    try:
        response = ask_ollama_improved(context, question)
    except Exception as e:
        print(f"Erreur lors de l'appel à ask_ollama_improved: {e}")
        response = "Désolé, j'ai rencontré un problème lors du traitement de votre demande. Veuillez reformuler votre question."

    data[question] = response
    save_data_to_file(data)
    return response

def main():
    print("Bienvenue dans l'outil de recherche d'informations avec Ollama Mistral!")
    print("Posez votre question (par exemple: 'Quel est le numéro de téléphone du Crous ?')")

    data = load_data_from_file()
    cached_data = load_cached_data()

    urls = {
        "https://api.parisnanterre.fr/aide-a-la-vie-etudiante": ["service", "aide", "vie étudiante"],
        "https://api.parisnanterre.fr/accueil-sha": ["service", "handicap", "sha", "aide"],
        "https://bu.parisnanterre.fr/travailler-en-groupe": ["bibliothèque", "BU", "étude", "groupe", "travailler", "salle"],
        "https://candidatures-inscriptions.parisnanterre.fr/accueil/faq-redoubler-dans-une-formation": ["inscription","redoubler","FAQ","scolarité","formation"],
        "https://aca2.parisnanterre.fr/agenda": ["association", "agenda", "événement", "aca2", "activité"],
        "https://api.parisnanterre.fr/faq": ["service", "handicap", "faq", "sha", "aide"],
        "https://etudiants.parisnanterre.fr/precarite-les-dispositifs-daide-a-luniversite" : ["aide", "aide étudiant", "précarité", "services aide"],
        "https://api.parisnanterre.fr/accueil-suio": ["service", "aide"],
        "https://www.crous-versailles.fr/": ["services étudiants", "aides financières", "solidarité étudiante"],
        "https://www.crous-versailles.fr/contacts/": ["contacts", "aide étudiante", "CROUS", "logement"],
        "https://www.crous-versailles.fr/contacts/bourses-et-aides-financieres/": ["bourses", "aides financières",
                                                                                   "CROUS", "précarité étudiante"],
        "https://www.crous-versailles.fr/contacts/social-et-accompagnement/": ["aide sociale", "accompagnement",
                                                                               "CROUS", "solidarité étudiante"],
        "https://www.crous-versailles.fr/contacts/logement-et-vie-en-residence/": ["logement étudiant",
                                                                                   "vie en résidence", "CROUS",
                                                                                   "aide au logement"],
        "https://www.crous-versailles.fr/contacts/compte-izly/": ["compte Izly", "CROUS", "services étudiants",
                                                                  "paiement universitaire"],
        "https://www.lescrous.fr/2024/09/comment-beneficier-du-repas-crous-a-1e/#:~:text=Ainsi%20tous%20les%20%C3%A9tudiants%20peuvent,ou%20en%20situation%20de%20pr%C3%A9carit%C3%A9" : ["restaurant universitaire Crous", "ru", "tarif", "prix", "repas", "repas 1 euro"],
        "https://www.crous-versailles.fr/contacts/contribution-vie-etudiante-et-de-campus-cvec/": ["CVEC", "vie étudiante", "contribution universitaire", "CROUS"],
        "https://www.iledefrance-mobilites.fr/titres-et-tarifs": ["transport"],
        "https://www.iledefrance-mobilites.fr/titres-et-tarifs/detail/forfait-imagine-r-scolaire": ["transport"],
        "https://www.iledefrance-mobilites.fr/titres-et-tarifs/detail/forfait-imagine-r-etudiant": ["transport"],
        "https://www.iledefrance-mobilites.fr/imagine-r/simulateur": ["transport"],
        "https://www.iledefrance-mobilites.fr/imagine-r#slice": ["transport"],
        "https://www.iledefrance-mobilites.fr/aide-et-contacts/nous-ecrire?type=information&motif=objets-trouves": ["transport"],
        "https://www.iledefrance-mobilites.fr/aide-et-contacts": ["transport"],
        "https://www.iledefrance-mobilites.fr/aide-et-contacts/generalites-supports-validations": ["transport"],
        "https://www.iledefrance-mobilites.fr/aide-et-contacts/generalites-supports-validations/comment-obtenir-un-forfait-imagine-r-et-ou-une-carte-de-transport-scolaire": ["transport"],
        "https://www.1jeune1solution.gouv.fr/logements/annonces?annonce-de-logement%5Brange%5D%5Bsurface%5D=0%3A500&annonce-de-logement%5Brange%5D%5Bprix%5D=0%3A3000": ["logement"],
        "https://www.1jeune1solution.gouv.fr/logements/aides-logement": ["logement"],
        "https://bienvenue.parisnanterre.fr/vie-du-campus/restauration-et-autres-lieux-de-convivialite": ["restaurant","manger", "restauration", "cafet", "cafétariat"],
        "https://licence.math.u-paris.fr/informations/modalites-de-controle-des-connaissances/#:~:text=Validation%20du%20dipl%C3%B4me&text=Une%20ann%C3%A9e%20est%20valid%C3%A9e%20si,les%20six%20semestres%20sont%20valid%C3%A9s" : ["licence", "valider", "crédits", "validation année", "valider semestre"],
        "https://www.1jeune1solution.gouv.fr/logements/conseils": ["logement"],
        "https://suaps.parisnanterre.fr/la-piscine": ["sport", "suaps", "activités nautiques"],
        "https://suaps.parisnanterre.fr/la-salle-cardio": ["sport", "suaps", "éducation corporelle et remise en forme",
                                                           "fitness"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites": ["sport", "suaps"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/les-sports-collectifs": ["sport", "suaps", "sport collectif"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/basket-ball": ["sport", "suaps", "basket-ball","sport collectif"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/futsal": ["sport", "suaps", "futsal",
                                                                          "sport collectif"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/handball": ["sport", "suaps", "handball",
                                                                            "sport collectif"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/rugby": ["sport", "suaps", "rugby", "sport collectif"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/tchoukball-kabadji": ["sport", "suaps", "tchoukball",
                                                                                      "sport collectif"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/volley-ball": ["sport", "suaps", "volley-ball",
                                                                               "sport collectif"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/les-sports-individuels": ["sport", "suaps",
                                                                                          "sport individuel"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/athletisme": ["sport", "suaps", "athlétisme",
                                                                              "sport individuel"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/escalade": ["sport", "suaps", "escalade",
                                                                            "sport individuel"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/tir-a-larc": ["sport", "suaps", "tir à l'arc",
                                                                              "sport individuel"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/les-sports-de-raquettes": ["sport", "suaps",
                                                                                           "sport de raquettes"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/badminton": ["sport", "suaps", "badminton",
                                                                             "sport de raquettes"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/tennis": ["sport", "suaps", "tennis",
                                                                          "sport de raquettes"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/tennis-de-table": ["sport", "suaps", "tennis de table",
                                                                                   "sport de raquettes"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/les-sports-de-combat": ["sport", "suaps",
                                                                                        "sport de combat"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/jiu-jitsu": ["sport", "suaps", "jiu-jitsu",
                                                                             "sport de combat"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/boxe": ["sport", "suaps", "boxe", "sport de combat"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/judo": ["sport", "suaps", "judo", "sport de combat"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/mma-grappling": ["sport", "suaps", "mma",
                                                                                 "sport de combat"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/self-defense": ["sport", "suaps", "self-defense",
                                                                                "sport de combat"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/education-corporelle-et-remise-en-forme": ["sport",
                                                                                                           "suaps",
                                                                                                           "éducation corporelle et remise en forme"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/education-posturale": ["sport", "suaps",
                                                                                       "éducation posturale",
                                                                                       "éducation corporelle et remise en forme"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/fitness": ["sport", "suaps", "fitness",
                                                                           "éducation corporelle et remise en forme"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/musculation": ["sport", "suaps", "musculation",
                                                                               "éducation corporelle et remise en forme"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/arts-du-mouvement": ["sport", "suaps",
                                                                                     "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/arts-du-cirque": ["sport", "suaps", "arts du cirque",
                                                                                  "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/atelier-choregraphie": ["sport", "suaps",
                                                                                        "atelier chorégraphie",
                                                                                        "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/bachata": ["sport", "suaps", "bachata",
                                                                           "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/danse-africaine": ["sport", "suaps", "danse africaine",
                                                                                   "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/danse-contemporaine": ["sport", "suaps",
                                                                                       "danse contemporaine",
                                                                                       "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/zumba": ["sport", "suaps", "zumba",
                                                                         "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/tango-argentin": ["sport", "suaps", "tango argentin",
                                                                                  "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/salsa": ["sport", "suaps", "salsa",
                                                                         "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/rocknroll": ["sport", "suaps", "rock'n'roll",
                                                                             "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/piloxing": ["sport", "suaps", "piloxing",
                                                                            "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/kizomba": ["sport", "suaps", "kizomba",
                                                                           "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/hip-hop": ["sport", "suaps", "hip-hop",
                                                                           "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/danse-orientale": ["sport", "suaps", "danse orientale",
                                                                                   "arts du mouvement"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/activites-nautiques": ["sport", "suaps",
                                                                                       "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/aquabike-aquagym-circuit-training": ["sport", "suaps",
                                                                                                     "aquabike",
                                                                                                     "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/plongee": ["sport", "suaps", "plongée",
                                                                           "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/natation-perfectionnement": ["sport", "suaps",
                                                                                             "natation",
                                                                                             "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/natation-intermediaire": ["sport", "suaps", "natation",
                                                                                          "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/natation-competition": ["sport", "suaps", "natation",
                                                                                        "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/natation-apprentissage": ["sport", "suaps", "natation",
                                                                                          "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/bnssa": ["sport", "suaps", "BNSSA",
                                                                         "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/baignade-libre": ["sport", "suaps", "baignade libre",
                                                                                  "activités nautiques"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/activite-detente": ["sport", "suaps",
                                                                                    "activité détente"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/yoga": ["sport", "suaps", "yoga", "activité détente"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/taichi-qi-gong": ["sport", "suaps", "taichi",
                                                                                  "activité détente"],
        "https://suaps.parisnanterre.fr/les-sports-et-activites/relaxation": ["sport", "suaps", "relaxation",
                                                                              "activité détente"],
        "https://ufr-lce.parisnanterre.fr/associations": ["association", "annuaire"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/dix-de-choeur": ["association",
                                                                                                          "musique"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/melodix": ["association",
                                                                                                    "musique"],
        "http://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/la-volt": ["association",
                                                                                                   "musique"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/revolte-toi-nanterre": [
            "association", "éloquence et débat"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/les-unis-verts": [
            "association", "écologie"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/mun-society-paris-nanterre": [
            "association", "éloquence et débat"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/acfa": ["association",
                                                                                                 "représentation étudiante"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/amnesty-international-groupe-jeunes-3047": [
            "association", "caritatif"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/faun": ["association",
                                                                                                 "représentation étudiante"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/association-psychologie-du-developpement": [
            "association", "médias, lecture et écriture"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/les-indifferents": [
            "association", "théâtre"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/les-impunis-ligue-dimprovisation": [
            "association", "théâtre"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/eloquentia-nanterre": [
            "association", "éloquence et débat"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/lysias": ["association",
                                                                                                   "éloquence et débat"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/lcc-production": [
            "association", "audiovisuel/cinéma"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/nuits-noires": ["association",
                                                                                                         "audiovisuel/cinéma"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/atelier-decriture": [
            "association", "médias, lecture et écriture"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/lili-blooms-book-club": [
            "association", "médias, lecture et écriture"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/pile-a-lire": ["association",
                                                                                                        "médias, lecture et écriture"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/rcva": ["association",
                                                                                                 "culture scientifique"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/altiski": ["association",
                                                                                                    "sport"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/cheerleading-paris-nanterre-1": [
            "association", "sport"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/laocho": ["association",
                                                                                                   "sport"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/la-nav-nanterre-association-de-voile": [
            "association", "sport"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/aumonerie-catholique-des-etudiant-es": [
            "association", "solidarité et entraide"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/asega": ["association",
                                                                                                  "solidarité et entraide"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/cercle-marxiste-de-nanterre": [
            "association", "citoyenneté"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/etudiants-musulmans-de-france-nanterre": [
            "association", "solidarité et entraide"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/ucph": ["association",
                                                                                                 "solidarité et entraide"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/union-etudiants-juifs-france-nanterre": [
            "association", "solidarité et entraide"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/lathena": ["association",
                                                                                                    "caritatif"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/antenne-jeunes-unicef-nanterre": [
            "association", "caritatif"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/amicale-des-etudiant-es-senegalais-es": [
            "association", "cultures du monde"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/compagnie-ptdr": [
            "association", "théâtre"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/paris-nanterre-maroc-1": [
            "association", "cultures du monde"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/le-poing-leve": ["association",
                                                                                                          "citoyenneté"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/union-etudiante-nanterre": [
            "association", "représentation étudiante"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/unef-nanterre": ["association",
                                                                                                          "représentation étudiante"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/ugen-fse": ["association",
                                                                                                     "représentation étudiante"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/promet": ["association",
                                                                                                   "association de filiere, ssa, sciences sociales et administrations"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/hypothemuse": ["association",
                                                                                                        "association de filiere, ssa, sciences sociales et administrations"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/gang": ["association",
                                                                                                 "association de filiere, ssa, sciences sociales et administrations"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/enape": ["association",
                                                                                                  "association de filiere, ssa, sciences sociales et administrations"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/bde-staps-rhinos": [
            "association", "sciences et techniques des activites physiques et sportives (staps)"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/psychx": ["association",
                                                                                                   "sciences psychologiques et sciences de l'éducation (spse)"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/comite-dactions-et-reseau-des-etudiants-en-sante-et-societe": [
            "association", "sciences psychologiques et sciences de l'éducation (spse)"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/les-alhumes": ["association",
                                                                                                        "sciences psychologiques et sciences de l'éducation (spse)"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/cine-rebelle": ["association",
                                                                                                         "philosophie, information-communication, langage, littérature, arts du spectacle (phillia)"],
        "https://aca2.parisnanterre.fr/associations/annuaire-des-associations-etudiantes/association-west-street": [
            "association", "sciences economiques, gestion, mathematiques, infomatique (segmi)"],
    }
    while True:
        question = input("\nVotre question (ou tapez 'exit' pour quitter) : ").strip()

        if question.lower() == 'exit' :
            print("Au revoir !")
            break
            break

        # Trouver la réponse en fonction de la question
        response = asyncio.run(process_query(question, data, urls, cached_data))
        """response = asyncio.run(find_info_for_question(question, data, urls, cached_data))"""
        print(f"Réponse : {response}")


if __name__ == "__main__":
    main()