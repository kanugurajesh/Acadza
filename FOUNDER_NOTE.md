# Note for the AI Intern application (draft)

> If the tagging run finishes before you send, replace "12 of the 13 gold cases" with the final v3 gold score from REPORT.md §3.
> Send as the email body, with the CV attached. Offer the repo, report and review screen as a private link, not attachments,
> because they contain Acadza's question content.

---

**Subject:** AI Intern application: I audited 449 of Acadza's questions with AI (and found where AI gets it wrong)

Hi,

I'm applying for the AI Intern role. Instead of describing something I built elsewhere, I worked on Acadza itself.

**What I looked at.** I went through every student-facing DOST on a free account. Chanakya is already strong: it
solved a kinematics problem correctly, answered in Hinglish, and builds multi-step journeys. So I didn't build another
chatbot. What holds Chanakya and the sub-concept-level DOSTs back is the question data underneath. When I asked
Chanakya about my own assignment, it replied that the questions "are not visible here yet" and asked for a screenshot.

**What I measured** on 449 questions served by the Practice DOST (6 free Maths chapters × 3 levels):
- 20.7% have no concept or sub-concept tag; 13.6% store the question's maths as images (18.0% of solutions).
- 7.8% are served in an assignment for a different chapter. One binomial-coefficient question is tagged *Hyperbola*.
- None are marked `tagByAI` or teacher-tagged.

**What I built: a "Question Bank Doctor"** in Acadza's own format and syllabus (104 chapters, 2,423 sub-concepts,
read from the public site code).
1. MathML → LaTeX with plain code (349 questions, zero AI cost). Image-maths questions are rendered and read by a
   vision model (5 / 5 spot-checked transcriptions exact).
2. Tagging that can only output real Acadza syllabus entries (strict JSON enum).
3. Answer-key checking: a small model solves blind and only escalates disagreements, so 96% (122 of 127) are settled cheaply.
4. A review screen: original vs. clean question, old vs. new tag, evidence, accept/reject, export as a patch.

**The part I think matters most is where it went wrong.** My first tagger was *worse* than your existing tags. On 30
hand-labelled disagreements, your tags were right 27 times and it was right 12. It filed remainder problems under
"Mathematical Reasoning" because it saw only chapter names. A small gold set caught that before it could touch the
bank. The fixed version reads your sub-concept definitions (remainders → *Binomial → Application → Last digits*) and
so far gets 12 of the 13 gold cases it has re-tagged right (the rest of that run is waiting on API quota). Similarly, of the two answer keys it flagged, one was a real defect (a
single-correct question where (B) and (D) are both correct), and the other came from a bug in my own text
conversion, which I found by solving it by hand and then fixed. So I'd pitch AI here as triage: it turns 449
questions into a short list a teacher can check in minutes. It isn't an oracle.

**Cost:** about $0.19 in API calls for everything so far (Groq, open-weight models).

**Also noticed while exploring** (19 issues in all, each with evidence; happy to walk through them):
- Opening a chapter page silently creates an empty assignment and an empty test, every visit.
- The coaching test list shows faculty phone numbers to students.
- There are a couple of security-hygiene items in the public JS bundle that I'd rather share privately than by email.

I can share the code, the report and the review screen privately. I'd love to do the same for Physics and Chemistry,
and to work on the things this unlocks: automatic remedies, the "Adaptive (Coming soon)" level, and letting Chanakya
read a student's own questions.

Thanks,
⟨your name⟩
⟨phone · GitHub/LinkedIn⟩
