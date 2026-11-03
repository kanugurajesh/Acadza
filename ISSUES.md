# Issues found in the Acadza app

**When:** 3 Nov 2026 · **Where:** www.acadza.com (web) · **Account:** student, Silver (free) plan, coaching "99+JEE" / Testing Batch
**How:** logged-in walkthrough of every student-facing feature in Microsoft Edge, scripted with Playwright, plus
inspection of the network calls the app itself makes and the public JavaScript bundles. Nothing was purchased, no
test was submitted, and no setting was changed.

**Scope limits:** the free plan stops most DOST wizards past chapter selection, and teacher/admin screens are not
visible to a student account. Everything below was observed directly. Where something is an inference, it says so.

Severity guide: **High** = wrong data reaches students or exposes data · **Medium** = misleading or broken behaviour ·
**Low** = cosmetic / copy.

| # | Issue | Area | Severity |
|---|---|---|---|
| 1 | Opening a chapter page silently creates an empty assignment **and** an empty test | Study Material | High |
| 2 | Questions from other chapters are served in a chapter assignment (7.8%) | Practice DOST / question bank | High |
| 3 | 20.7% of questions have no concept / sub-concept tag | Question bank | High |
| 4 | Maths stored as images in questions (13.6%) and solutions (18.0%) | Question bank | High |
| 5 | Chanakya AI cannot read the questions in the student's own assignments | Chanakya | High |
| 6 | Faculty phone numbers are shown to students in the coaching test list | Acadza Tests | High (privacy) |
| 7 | Hard-coded auth token and a secret-like string in the public JS bundle | Security | Medium (token expired) |
| 8 | Tags differ from the syllabus by whitespace, so exact-match joins fail | Taxonomy | Medium |
| 9 | Score card / analysis messages for an unattempted test are misleading | Analysis | Medium |
| 10 | Empty placeholders: `percentile: (%)`, `Rank: ()`, `Pattern: JEE ( min)` | Lists | Low |
| 11 | Test subject mismatch ("Chemistry Test", Subject: Physics) | Acadza Tests | Low |
| 12 | Free-chapter messaging is inconsistent | Paywall | Medium |
| 13 | Pages that render blank: Parent Dost (`/dosts/parent`), Search question | Parent / Search | Medium |
| 14 | Wrong page header on Probable Question ("Backlog Remover DOST") | Revision | Low |
| 15 | Typos in UI copy and syllabus names | Copy / taxonomy | Low |
| 16 | Several copies of the syllabus ship in different bundles, with different sizes | Taxonomy | Info |
| 17 | Dev preview and admin routes are listed in the production build manifest | Security hygiene | Info |
| 18 | A single-correct question has two correct options | Question bank | Medium |
| 19 | Malformed MathML in stored solutions | Question bank | Low |

Product gaps (not bugs, but worth knowing) are listed at the end.

---

## 1. Opening a chapter page creates an empty assignment and an empty test — High
**What happens:** loading `/basket/concept?subject=…&chapter=…` (Study Material → any chapter) fires
`POST api.acadza.in/next/practice/create` **twice** with no user action, once with `practiceType: "assignment"` and once
with `practiceType: "test"`, both with `practicePortion: []`.

**Evidence:** network capture while only loading `/basket/concept?subject=Physics&chapter=Rotational+Motion`.
The responses were `"Assignment saved successfully!!"` and `"Test saved successfully!!"`.

**Impact:**
- The student's *Recent activity* fills with junk "Incomplete" items (this account gained test-2, assignment-3, test-4,
  assignment-5, test-6, assignment-7 just from browsing).
- Empty practice documents pile up in the database on every chapter visit, for every student and every white-label app.
- Any metric built on "assignments created" or "completion rate" is inflated or deflated.

**Likely fix:** create the practice document lazily, only when the student clicks *Assignment / Test / Mini Assignment /
Practice Me*. Clean up existing records with empty `practicePortion` and no attempts.

## 2. Questions from other chapters are served in chapter assignments — High
**What happens:** a Practice DOST assignment for one chapter includes questions whose `chapter` field is a different
chapter.

**Evidence:** 18 assignments (6 free Maths chapters × Easy/Medium/Hard, 449 unique questions). **35 / 449 (7.8%)**
carry a different chapter tag than the one requested. Examples:
- "Binomial Theorem" assignment → question tagged **Hyperbola**, whose text is about *binomial coefficients in the
  expansion of (1 + z)…*. The content matches the requested chapter, so the **tag looks wrong**.
- "Complex Numbers" assignment → two questions tagged **Matrices and Determinants** (a determinant of trig values, a
  matrix of cube roots of unity). These are genuinely multi-topic.
- "Sequences and Series" assignment → 13 off-chapter questions (Trigonometry ×3, Quadratic ×2, Limits, Vectors, 3-D
  Geometry…).
- "Quadratic Equations" assignment → trigonometry questions (e.g. *4cos²θ – 6sec²θ = 5*).

**Impact:** students get questions they haven't studied in a chapter-focused set. Danger areas, backlog plans and
remedies that read the chapter tag then attribute mistakes to the wrong chapter.

**Inference:** the off-chapter questions are probably selected through a secondary link (e.g. a related-concept mapping)
while the primary `chapter` tag says something else. Either the selector or the tag is wrong, and the API can't tell
which.

## 3. One in five questions has no concept / sub-concept tag — High
**Evidence:** **93 / 449 (20.7%)** have `concept` and `subConcept` empty. Spread across all six chapters (12–21 each).
59 of the 93 are also the legacy "maths-as-image" questions (#4).
Across all 449: `tagByAI` is `false` and `taggedByCoachingTeacher` is `false`.

**Impact:** the product is built on 2,423 JEE sub-concepts (Study Material, Formula Sheet, Backlog, Revision, Danger
Areas). An untagged question cannot add to sub-concept-level weak / slow / mistake areas, cannot be picked by
concept filters, and cannot feed a remedy.

## 4. Maths stored as images — High
**What happens:** older questions embed each formula as an `<img>` (S3 `acadza-check`) inside the question/solution
HTML, e.g. `If <img> are the roots of <img> then the roots of <img> shall be`.

**Evidence:** **61 / 449 (13.6%)** questions and **81 / 449 (18.0%)** solutions contain formula images. One sample
question alone had 7 formula images in the question and 5 in the solution.

**Impact:** the text of these questions is unreadable to search, de-duplication, auto-tagging, screen readers, and any
LLM (including Chanakya). The images also don't scale with dark mode or zoom.

## 5. Chanakya AI can't read the student's own questions — High
**Evidence:** asked Chanakya *"Look at my assignment 'probe-quadratic'. Which questions in it are not from Quadratic
Equations?"* It replied: *"its questions are not visible here yet. I need the question text or a clear
photo/screenshot."* Asked to *"analyse my 30 unattempted questions"*, it asked the student to upload images of the
questions.

**Impact:** the AI layer (which is otherwise strong: correct physics working, Hinglish, memory, 8-step journeys) can't
reach the question bank, which is the core asset. #4 makes this harder to fix.

## 6. Faculty phone numbers shown to students — High (privacy)
**What happens:** in **Acadza Tests** (`/pace/test-list`), each faculty test card shows `Faculty: <10-digit mobile
number>` instead of a name.

**Evidence:** three different faculty numbers visible on the 99+JEE test list (not reproduced here).

**Impact:** personal contact details of teachers at a white-label coaching client are exposed to every student in the
batch.

**Fix:** show the faculty display name; never send the phone number to student clients.

## 7. Hard-coded auth token and a secret-like string in the public bundle — Medium
**What happens:** the public JS chunk for `/chatbot-new` contains a hard-coded `Bearer` JWT for a user with
`role: "teacher"`, and a string literal named like a secret (`SECRET_DO_NOT_…`).

**Evidence:** found by reading the public, unauthenticated JS file served by www.acadza.com. The JWT's `exp` decodes to
May 2025, so it looks expired. **I did not try to use it.** The values are not reproduced here.

**Impact:** low today because the token has expired. But it shows that credentials have been committed into front-end code,
and a future non-expired token in the same place would grant teacher-level API access to anyone.

**Fix:** remove it from the source, rotate the signing secret if that token was ever valid in production, and add a
secret scanner (e.g. gitleaks) to CI.

## 8. Tags differ from the syllabus by whitespace — Medium
**Evidence:** 13 / 449 questions are tagged `Finding Coefficient of xʳ` while the syllabus shipped to the browser
has `Finding␣␣Coefficient of xʳ` (two spaces). After normalising whitespace they match, so it's not real drift.

**Impact:** any exact string join (question ↔ sub-concept basket, danger-area aggregation, formula sheet lookup) silently
drops these questions.

**Fix:** use IDs for sub-concepts instead of display strings, or normalise on write.

## 9. Misleading analysis for an unattempted test — Medium
**Evidence:** *Get analysis* on an unattempted test shows "Your test is finished", empty marks (`TOTAL MARKS OBTAINED /`),
`0/5` speed and accuracy stars, and *"You are quick ⚡ but accuracy was 0. Slow down a little and focus on
correctness."* for **0 questions attempted**.

**Fix:** show an empty state ("You haven't attempted this test yet") when the attempt count is 0.

## 10. Empty placeholders in lists — Low
`percentile: (%)` on Practice DOST tests, `Rank: ()` and `Pattern : JEE ( min)` on Acadza Tests cards: the template
renders even when the value is missing. Hide the field when it's empty.

## 11. Test subject mismatch — Low
On Acadza Tests, a card titled **"Chemistry Test"** shows **Subject: Physics**. Full papers such as "25 NOV ADV P1"
show a single subject (Chemistry). The subject shown appears to be the first subject only.

## 12. Inconsistent free-chapter messaging — Medium
- Every DOST page shows *"You can access 99+jee with these FREE chapters! Maths Trignometric Ratios, Functions &
  Identities"*, but **Teach Me** on a sub-concept in that same chapter opened the Gold-plan purchase popup.
- The assignment wizard instead offers six other Maths chapters as free (Quadratic, Sequences & Series, Binomial,
  P&C, Probability, Complex Numbers), which the banner doesn't mention.

A student can't tell what they can actually use for free.

## 13. Pages that render blank — Medium
- `/dosts/parent` (Parent Dost) rendered no content.
- `/dosts/search-question` rendered no visible content.

(Observed with a free student account; they may depend on a parent link or a paid plan. If so, they need an empty
state that explains why.)

## 14. Wrong page header — Low
`/dosts/probable-question` (the "5 most probable" revision tool) shows the header **"Backlog Remover DOST"** and
*"Create new plan / No Plan Created"*.

## 15. Typos — Low
- UI: *"Predict **petcentage** marks you'll score…"* (Syllabus Update dialog).
- Syllabus names (these are also used as keys, so fixing them needs a migration): *Trignometric* Ratios, *Colision* of one
  direction, *Quotent* rule, General *Characterictics* of f block, *Lantanoid* Contraction.

## 16. Several copies of the syllabus in the front-end — Info
The syllabus tree is bundled in at least five JS chunks. The JEE tree matching the UI ("1 of 838 sub-concepts")
has Physics 30 chapters / 220 concepts / 838 sub-concepts, but another chunk ships a Physics tree with 30 / 202 / 659,
and another with 34 / 171 / 530. Some are probably other exam modes (NCERT/MHCET/Boards), but differing copies are a
likely source of #8-style mismatches. Worth one source of truth served from the API.

## 17. Dev and admin routes in the production build manifest — Info
The public `_buildManifest.js` lists `/dev/*` preview pages (e.g. `/dev/assignment-preview`, `/dev/marking-editor-preview`)
and admin pages (e.g. `/blogs/dashboard`, `/olympiads/admin`, `/lecture-schedule-admin`, `/pace/faculty-admin-test-list`).
**I did not test whether they're access-controlled.** Listing them isn't a vulnerability by itself, but dev previews
usually shouldn't ship, and admin pages should be checked for server-side auth.

## 18. A single-correct question with two correct options — Medium
**Found by:** the Doctor's answer-key check. Two independent models chose (D) while the key says (B), and Acadza's own
worked solution supports (B). Solved by hand to settle it.

**Question:** `6a62745a9fc11309026096c9`, *Value of Σ_{k=1}^{n} C_k·C_{k−1}* (Binomial Theorem, single-correct).
The sum is ²ⁿC_{n−1}. Option (D) ²ⁿC_{n+1} equals that by symmetry, and option (B) ½·²ⁿ⁺²C_{n+1} − ²ⁿC_n
simplifies to it too. **Both (B) and (D) are correct**, so a student who picks (D) loses marks for a right answer.

**Fix:** change option (D), or make it multi-correct with key [B, D].

(In the 127-question sample, 126 keys were confirmed by an independent solve. This is the only confirmed defect. A
second flag turned out to be a bug in the Doctor's own text conversion and is **not** an Acadza error.)

## 19. Malformed MathML in stored solutions — Low
4 solutions in the 449-question sample contain MathML that isn't well-formed XML (mismatched closing tags, a bare `&`
inside `<mi>`). Browsers render it leniently, but any tool that parses the maths (search, LaTeX export,
accessibility, AI) fails on those fragments. Worth validating MathML when questions are saved in the editor.

---

## Product gaps (not bugs)
- **Remedies are built by hand:** *"Remedies appear here when your faculty builds one from a paper you have sat."*
- **Mistake type is self-labelled:** the *Your mistakes* page filters by "Type of mistake". Chanakya asks students to label
  skipped questions themselves ("time shortage, concept gap, or hesitation").
- **Adaptive difficulty** is listed as *"Adaptive (Coming soon)"* in the assignment wizard.
- **Syllabus status is self-reported** (Red / Yellow / Green chapters, parent "Syllabus Update") rather than derived from
  attempts.

All four depend on reliable question text and tags (#2–#4), which is what the Question Bank Doctor in this repo addresses.
