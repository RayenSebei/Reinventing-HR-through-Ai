import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../sentinel_hr/fixtures')
const profiles = {
  'demo_en_software_support.pdf': {
    name: 'Morgan Example',
    body: `<h1>SOFTWARE SUPPORT ANALYST</h1><p class="meta">Synthetic profile · Fictional candidate · Lyon, France</p>
      <h2>Profile</h2><p>Early-career analyst with experience supporting internal software users, maintaining clear incident notes, and checking small data-processing changes before release.</p>
      <h2>Experience</h2><h3>Northstar Cooperative — Junior Support Analyst <span>2030–2032</span></h3>
      <ul><li>Used Python scripts to validate weekly CSV imports and summarize rejected rows for the data team.</li>
      <li>Reproduced reported defects, documented steps to reproduce, and kept a regression test checklist for monthly releases.</li>
      <li>Worked with a teammate to review changes in Git and wrote concise commit messages for support fixes.</li></ul>
      <h3>Open Workshop — Technology Volunteer <span>2029–2030</span></h3><ul><li>Prepared short how-to guides and helped new members use shared laptops and open-source tools.</li></ul>
      <h2>Selected project</h2><p><strong>CSV quality checker:</strong> built a small Python command-line utility to flag missing fields, duplicate rows, and unexpected date formats; added sample inputs and a README.</p>
      <h2>Education and learning</h2><p>Applied Computing Certificate, fictional Rhône Learning Institute, 2029.</p>
      <h2>Languages</h2><p>French (fluent), English (professional), Arabic (conversational).</p>`
  },
  'demo_en_quality_assistant.pdf': {
    name: 'Riley Example',
    body: `<h1>QUALITY ASSURANCE ASSISTANT</h1><p class="meta">Synthetic profile · Fictional candidate · Marseille, France</p>
      <h2>Summary</h2><p>Junior QA practitioner focused on careful test notes, accessible bug reports, and practical collaboration with product and engineering teams.</p>
      <h2>Experience</h2><h3>Fictional Harbor Apps — QA Assistant <span>2031–2033</span></h3><ul>
      <li>Maintained a Python utility that compared anonymized sample exports and identified unexpected changes.</li>
      <li>Planned exploratory sessions for account and reporting features; recorded expected results, observed behavior, and browser details.</li>
      <li>Created and updated regression scenarios after fixes, then discussed release risks with the engineering lead.</li>
      <li>Used Git branches and pull-request review to update test data and shared documentation.</li></ul>
      <h3>Community Repair Lab — Digital Projects Intern <span>2030–2031</span></h3><ul><li>Helped document inventory workflows and checked data-entry forms with volunteers.</li></ul>
      <h2>Project</h2><p>Designed a sample test strategy for a room-booking app, covering validation, keyboard navigation, and time-zone boundaries.</p>
      <h2>Education</h2><p>Diploma in Software Testing, fictional Coastline Technical School, 2030.</p>
      <h2>Tools</h2><p>Python, Git, issue tracking, browser dev tools, spreadsheets, basic SQL.</p>`
  },
  'demo_en_data_operations.pdf': {
    name: 'Avery Example',
    body: `<h1>DATA OPERATIONS TRAINEE</h1><p class="meta">Synthetic profile · Fictional candidate · Brussels, Belgium</p>
      <h2>Profile</h2><p>Careful early-career data operations contributor with experience checking scheduled imports and explaining data issues to non-technical colleagues.</p>
      <h2>Experience</h2><h3>Example Civic Lab — Data Operations Trainee <span>2030–2032</span></h3><ul>
      <li>Wrote Python scripts to normalize sample CSV files and produce a daily exception report.</li>
      <li>Compared pipeline outputs against documented examples and recorded a repeatable test strategy for each data source.</li>
      <li>Tracked configuration changes in Git and reviewed diffs with the analyst responsible for a release.</li>
      <li>Added plain-language notes describing the cause and impact of common validation failures.</ul>
      <h2>Project work</h2><p>Built a fictional transit-data quality dashboard using a local sample dataset; documented assumptions and tested empty, duplicate, and out-of-range values.</p>
      <h2>Education</h2><p>Certificate, Data Fundamentals, fictional Brussels Learning Exchange, 2029.</p>
      <h2>Languages</h2><p>French, Dutch, and English.</p>`
  },
  'demo_fr_quality_analyst.pdf': {
    name: 'Inès Exemple',
    lang: 'fr',
    body: `<h1>ASSISTANTE QUALITÉ LOGICIELLE</h1><p class="meta">Profil synthétique · Candidate fictive · Toulouse, France</p>
      <h2>Profil</h2><p>Début de carrière en assurance qualité, avec une expérience de tests fonctionnels, de rédaction de tickets reproductibles et de suivi de versions.</p>
      <h2>Expérience</h2><h3>Atelier Numérique Exemple — Assistante QA <span>2030–2032</span></h3><ul>
      <li>Écriture de scripts Python pour contrôler des exports CSV anonymisés et signaler les lignes incohérentes.</li>
      <li>Préparation d'une stratégie de test pour les parcours d'inscription et de recherche; vérification des résultats attendus et observés.</li>
      <li>Mise à jour d'une liste de tests de régression après correction des anomalies.</li>
      <li>Utilisation de Git pour proposer des changements à la documentation et aux données de test.</li></ul>
      <h3>Association Exemple — Bénévole numérique <span>2029–2030</span></h3><ul><li>Accompagnement des membres dans l'utilisation d'outils collaboratifs.</li></ul>
      <h2>Projet</h2><p>Prototype de vérificateur de données: règles de champs obligatoires, dates et doublons; exemples d'entrée et guide d'utilisation rédigés en français.</p>
      <h2>Formation</h2><p>Certificat de développement logiciel, Institut fictif des Métiers du Numérique, 2029.</p>
      <h2>Langues</h2><p>Français (courant), anglais (professionnel).</p>`
  },
  'demo_ar_it_support.pdf': {
    name: 'سلمى مثال',
    lang: 'ar',
    body: `<div dir="rtl" lang="ar"><h1>مساعدة دعم البرمجيات</h1><p class="meta">سيرة ذاتية تجريبية · مرشحة خيالية · ليون، فرنسا</p>
      <h2>نبذة</h2><p>مساهمة مبتدئة في دعم المستخدمين واختبار التغييرات الصغيرة وتوثيق خطوات معالجة المشكلات.</p>
      <h2>الخبرة</h2><h3>مختبر الميناء الافتراضي — مساعدة دعم <span>٢٠٣٠–٢٠٣٢</span></h3><ul>
      <li>كتابة نصوص Python للتحقق من ملفات CSV التجريبية والإبلاغ عن الحقول غير المكتملة.</li>
      <li>تسجيل خطوات إعادة إنتاج الأعطال ونتائج الاختبار المتوقعة والفعلية.</li>
      <li>إعداد قائمة اختبارات انحدار بعد تحديثات التطبيق ومناقشة النتائج مع الفريق.</li>
      <li>استخدام Git لمراجعة تغييرات التوثيق وملفات الاختبار.</li></ul>
      <h2>مشروع مختار</h2><p>أداة تدريبية لفحص جودة البيانات، مع أمثلة للاختبار ووثيقة تشرح حدود الاستخدام.</p>
      <h2>التعليم</h2><p>شهادة أساسيات الحوسبة، معهد تعليمي خيالي، ٢٠٢٩.</p>
      <h2>اللغات</h2><p>العربية، الفرنسية، والإنجليزية.</p></div>`
  },
  'demo_mixed_product_qa.pdf': {
    name: 'Adam Exemple',
    lang: 'en',
    body: `<h1>JUNIOR PRODUCT QA</h1><p class="meta">Synthetic profile · Fictional candidate · Montréal, Canada</p>
      <h2>Profile</h2><p>Multilingual software-testing trainee who enjoys turning user reports into clear examples, test notes, and small repeatable tools.</p>
      <h2>Experience</h2><h3>Fictional North Shore Studio — Product QA Intern <span>2031–2033</span></h3><ul>
      <li>Used Python to inspect anonymized CSV fixtures and summarize malformed records for the product team.</li>
      <li>Explained a test strategy for a multilingual booking flow, including keyboard navigation and date formatting.</li>
      <li>Maintained regression scenarios in Git and reviewed code and test-data changes with a mentor.</li>
      <li>Wrote release notes in French and English and helped triage reported issues.</li></ul>
      <h2>Project</h2><p>Created an example bug-report template that records steps, expected behavior, observed behavior, and accessibility context.</p>
      <h2>Formation / Education</h2><p>Programme de développement logiciel, fictional Montréal Tech Cooperative, 2030.</p>
      <h2>Languages</h2><p>French (fluent), English (fluent), Arabic (basic).</p>`
  },
  'demo_en_cloud_intern.pdf': {
    name: 'Jordan Example',
    body: `<h1>SOFTWARE OPERATIONS INTERN</h1><p class="meta">Synthetic profile · Fictional candidate · Rotterdam, Netherlands</p>
      <h2>Summary</h2><p>Early-career operations contributor with a foundation in scripting, careful change review, and collaborative incident follow-up.</p>
      <h2>Experience</h2><h3>Example Cloud Workshop — Operations Intern <span>2030–2032</span></h3><ul>
      <li>Built Python scripts for checking sample service logs and preparing weekly CSV summaries.</li>
      <li>Followed documented test strategies for configuration updates and added regression checks for known edge cases.</li>
      <li>Used Git to track changes to runbooks, sample scripts, and test fixtures.</li>
      <li>Shared concise incident timelines and asked a reviewer to approve operational changes.</li></ul>
      <h2>Project</h2><p>Local monitoring exercise with fictional services; documented warning thresholds, test inputs, and recovery steps.</p>
      <h2>Education and development</h2><p>Applied IT diploma, fictional Delta Technical Institute, 2029. Introductory coursework in networks and secure operations.</p>
      <h2>Languages</h2><p>Dutch, English, French (intermediate).</p>`
  },
}

const css = `@page{size:A4;margin:0}*{box-sizing:border-box}body{font-family:Arial,"DejaVu Sans",sans-serif;font-size:10.5pt;line-height:1.42;margin:42px 48px;color:#17212b}
h1{font-size:20pt;line-height:1.15;margin:0 0 7px;color:#12283a}h2{font-size:12pt;margin:17px 0 5px;padding-bottom:3px;border-bottom:1px solid #9aabb8;text-transform:uppercase;letter-spacing:.04em}
h3{font-size:10.5pt;margin:10px 0 4px}p,li{margin:3px 0}ul{padding-inline-start:20px;margin-block:4px 8px}.meta{color:#53677b;font-size:9pt}.meta:after{content:"";display:block;width:60px;border-bottom:3px solid #187567;margin-top:12px}h3 span{float:inline-end;font-weight:400;color:#53677b;font-size:9pt}`

await mkdir(root, { recursive: true })
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage()
  for (const [filename, profile] of Object.entries(profiles)) {
    const body = `<main><h1>${profile.name} — SYNTHETIC CV</h1>${profile.body}</main>`
    const lang = profile.lang ?? 'en'
    await page.setContent(`<html lang="${lang}"><head><meta charset="utf-8"><style>${css}</style></head><body>${body}</body></html>`)
    await page.pdf({ path: path.join(root, filename), format: 'A4', printBackground: true })
    console.log(`Generated ${filename}`)
  }
} finally {
  await browser.close()
}
