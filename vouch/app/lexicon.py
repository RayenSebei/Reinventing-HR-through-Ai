"""Multilingual skill word list (EN / FR / AR) used when no AI model is available,
and to widen what a criterion matches. Extend freely: canonical name -> aliases."""

SKILLS: dict[str, list[str]] = {
    "python": ["python", "py", "pandas", "بايثون"],
    "javascript": ["javascript", "js", "ecmascript", "node.js", "nodejs", "جافاسكريبت"],
    "typescript": ["typescript", "ts"],
    "sql": ["sql", "postgresql", "mysql", "sqlite", "base de données", "bases de données", "قواعد البيانات"],
    "git": ["git", "github", "gitlab", "version control", "contrôle de version", "gestion de version", "التحكم في الإصدارات"],
    "testing": ["test strategy", "test plan", "testing", "regression checklist", "regression", "unit test",
                "stratégie de test", "plan de test", "tests unitaires", "اختبار", "خطة الاختبار"],
    "docker": ["docker", "container", "conteneur"],
    "kubernetes": ["kubernetes", "k8s"],
    "machine learning": ["machine learning", "ml", "apprentissage automatique", "التعلم الآلي"],
    "communication": ["communication", "presentation", "présentation", "التواصل"],
    "leadership": ["leadership", "led a team", "team lead", "chef d'équipe", "قيادة"],
    "react": ["react", "react.js", "reactjs"],
    "java": ["java"],
    "linux": ["linux", "bash", "shell"],
}

# Words that carry no meaning when matching a criterion label to text.
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "and", "or", "to", "with", "for", "use", "used", "using",
    "ability", "able", "demonstrated", "experience", "knowledge", "familiarity", "required",
    "requirement", "skills", "skill", "strong", "good", "basic", "explain", "software", "project",
    "de", "la", "le", "les", "des", "et", "en", "du", "une", "un", "connaissance", "maîtrise",
}
