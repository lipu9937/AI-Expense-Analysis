import json
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
CATEGORIES = ["Food & Dining", "Groceries", "Transport", "Shopping", "Bills & Utilities",
              "Rent & Housing", "Entertainment", "Subscriptions", "Health", "Education",
              "Travel", "Personal Care", "EMI & Loans", "Investments", "Other"]

GUARD = ("You are a careful personal finance assistant. Currency is Indian Rupees (₹). "
         "Use ONLY the numbers present in the DATA JSON provided. Never invent, estimate or "
         "round differently than the data; if something is not in the data, say so. "
         "Be practical, specific and concise. ")

RULES = {
    "Food & Dining": ["swiggy", "zomato", "restaurant", "cafe", "pizza", "burger", "dominos", "kfc", "bakery", "hotel"],
    "Groceries": ["bigbasket", "blinkit", "zepto", "grocery", "supermarket", "dmart", "mart", "vegetable"],
    "Transport": ["uber", "ola", "rapido", "metro", "petrol", "fuel", "irctc", "bus", "parking", "fastag"],
    "Shopping": ["amazon", "flipkart", "myntra", "ajio", "meesho", "mall", "store"],
    "Bills & Utilities": ["electricity", "water bill", "gas", "broadband", "recharge", "airtel", "jio", "vodafone", "dth"],
    "Rent & Housing": ["rent", "maintenance", "society"],
    "Entertainment": ["movie", "bookmyshow", "pvr", "inox", "game", "concert"],
    "Subscriptions": ["netflix", "spotify", "prime", "hotstar", "youtube", "subscription", "icloud"],
    "Health": ["pharmacy", "apollo", "hospital", "clinic", "medical", "doctor", "diagnostic"],
    "Education": ["course", "udemy", "school", "college", "tuition", "coursera"],
    "Travel": ["makemytrip", "goibibo", "airlines", "indigo", "flight", "oyo", "airbnb"],
    "Personal Care": ["salon", "spa", "gym", "cult"],
    "EMI & Loans": ["emi", "loan", "credit card payment"],
    "Investments": ["sip", "mutual fund", "zerodha", "groww", "ppf", "nps"],
}


class LLMError(Exception):
    pass


def get_provider():
    p = os.getenv("LLM_PROVIDER", "").strip().lower()
    if p in ("openai", "gemini"):
        return p
    if os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        return "gemini"
    return PROVIDER or "openai"


def available():
    p = get_provider()
    key = os.getenv("OPENAI_API_KEY" if p == "openai" else "GEMINI_API_KEY", "").strip()
    return bool(key) and not key.startswith("your-")


def ask(system, user, json_mode=False, history=None):
    if not available():
        raise LLMError("No API key found. Add your key to the .env file and restart the app.")
    history = history or []
    p = get_provider()
    try:
        if p == "openai":
            from openai import OpenAI
            msgs = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user}]
            kw = {"response_format": {"type": "json_object"}} if json_mode else {}
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            client = OpenAI(api_key=api_key)
            r = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), messages=msgs, temperature=0.2, **kw)
            return r.choices[0].message.content
        from google import genai
        from google.genai import types
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        prompt_content = f"{convo}\nuser: {user}".strip() if convo else user
        preferred_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
        if preferred_model in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-2.0-flash-exp"):
            preferred_model = "gemini-3.5-flash"

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())
        models_to_try = [preferred_model]
        for fallback in ("gemini-3.5-flash", "gemini-3.8-flash"):
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_err = None
        for m in models_to_try:
            try:
                r = client.models.generate_content(
                    model=m,
                    contents=prompt_content,
                    config=types.GenerateContentConfig(
                        system_instruction=system, temperature=0.2,
                        response_mime_type="application/json" if json_mode else None))
                return r.text
            except Exception as err:
                last_err = err
                continue
        raise last_err
    except Exception as e:  # network, quota, auth ...
        raise LLMError(f"LLM request failed: {e}") from e


def rule_category(desc):
    d = desc.lower()
    for cat, words in RULES.items():
        if any(w in d for w in words):
            return cat
    return "Other"


def categorize(descriptions):
    """Returns ({description: category}, used_llm: bool). Falls back to keyword rules."""
    uniq = list(dict.fromkeys(d.strip() for d in descriptions))
    result, used_llm = {}, False
    for i in range(0, len(uniq), 40):
        chunk = uniq[i:i + 40]
        try:
            prompt = (f"Categories: {CATEGORIES}\nClassify each transaction description into exactly one "
                      f"category. Return JSON: {{\"categories\": [...]}} with the same length and order "
                      f"as this list:\n{json.dumps(chunk)}")
            out = json.loads(ask("You classify bank transactions. Reply with JSON only.", prompt, json_mode=True))
            cats = out["categories"]
            if len(cats) != len(chunk):
                raise ValueError("length mismatch")
            for d, c in zip(chunk, cats):
                result[d] = c if c in CATEGORIES else rule_category(d)
            used_llm = True
        except Exception:
            for d in chunk:
                result[d] = rule_category(d)
    return result, used_llm
