from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT = "CICD_Healing_Agent_Research_Paper_24_References.pdf"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="PaperTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="Authors", parent=styles["Normal"], fontName="Helvetica",
    fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#3D4A5C"),
    spaceAfter=14,
))
styles.add(ParagraphStyle(
    name="Abstract", parent=styles["Normal"], fontName="Helvetica",
    fontSize=8.7, leading=12, alignment=TA_JUSTIFY, leftIndent=8*mm,
    rightIndent=8*mm, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="Section", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=11.5, leading=14, textColor=colors.HexColor("#173B63"),
    spaceBefore=9, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="Subsection", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=9.8, leading=12, textColor=colors.HexColor("#245B85"),
    spaceBefore=6, spaceAfter=3,
))
styles.add(ParagraphStyle(
    name="Body", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=8.7, leading=11.8, alignment=TA_JUSTIFY, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="Small", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=7.5, leading=9.5, spaceAfter=3,
))
styles.add(ParagraphStyle(
    name="CodeBlock", parent=styles["BodyText"], fontName="Courier",
    fontSize=7.2, leading=9, leftIndent=5*mm, rightIndent=5*mm,
    textColor=colors.HexColor("#203040"), backColor=colors.HexColor("#F1F5F9"),
    borderPadding=5, spaceBefore=3, spaceAfter=6,
))


def P(text, style="Body"):
    return Paragraph(text, styles[style])


def table(data, widths):
    converted = []
    for row in data:
        converted.append([cell if isinstance(cell, Paragraph) else P(str(cell), "Small") for cell in row])
    result = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173B63")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C7D8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F7FAFC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FB")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return result


def footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#B8C7D8"))
    canvas.line(18*mm, 14*mm, 192*mm, 14*mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#6B7785"))
    canvas.drawString(18*mm, 9*mm, "CICD Healing Agent - Implementation research paper")
    canvas.drawRightString(192*mm, 9*mm, f"Page {document.page}")
    canvas.restoreState()


class PaperDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(filename, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                         topMargin=16*mm, bottomMargin=20*mm, title="CICD Healing Agent")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="paper", frames=frame, onPage=footer)])


story = []
story += [
    P("CICD Healing Agent: A Self-Healing CI/CD Pipeline with Error Memory and Validated AI Repair", "PaperTitle"),
    P("Ramani G1, Kavya K M2, Harshith S3, Chethan Rao G K4, Vinay Raghav M5<br/>Department of Computer Science and Engineering (AI &amp; ML), AMC Engineering College, Bengaluru, Karnataka, India", "Authors"),
    P("<b>Abstract</b> - This paper presents CICD Healing Agent, a code-centric self-healing CI/CD prototype for Python repositories. The implemented system accepts a GitHub repository, clones it into an isolated workspace, creates a repair branch when credentials are available, executes pytest inside Docker, reduces noisy logs, extracts a structured failure, checks a SQLite error-memory database, and either reuses a previously validated repair or invokes OpenRouter to generate a new candidate. A candidate is written to the requested target file and validated by running the tests again. Successful changes can be committed, pushed, and used to create a GitHub pull request. The system is intentionally bounded by retry limits and keeps secrets outside the user interface. This revised paper distinguishes implemented behavior from future extensions such as GitHub Actions polling, multi-agent orchestration, and production-scale deployment.", "Abstract"),
    P("<b>Index Terms</b> - CI/CD, self-healing pipelines, DevOps automation, AIOps, automated program repair, large language models, error memory, Docker, OpenRouter, GitHub", "Abstract"),
]

story += [P("I. INTRODUCTION", "Section")]
story += [
    P("Modern software delivery depends on automated integration and testing, but failures still require engineers to read logs, locate the fault, edit source code, and rerun validation. Common causes include assertion failures, incorrect exception behavior, missing dependencies, syntax errors, and configuration mistakes. Conventional pipelines stop at failure and expose evidence; they do not normally close the loop by producing and validating a repair."),
    P("CICD Healing Agent addresses this gap with a bounded detect-analyze-repair-validate loop. Its focus is application-level repair rather than infrastructure rollback. The system combines a FastAPI backend, a lightweight HTML/CSS/JavaScript dashboard, Docker-based test execution, OpenRouter code generation, SQLite persistence, and GitHub branch and pull-request operations."),
    P("The main contributions of the implemented prototype are: (1) a working repository-to-repair workflow; (2) an error memory that stores validated source repairs and reuses them without an unnecessary AI call; (3) log processing that separates actionable failure information from raw test output; and (4) governed delivery through a dedicated branch, commit, push, and optional pull request."),
]

story += [P("II. RELATED WORK", "Section")]
story += [
    P("Conventional CI/CD systems automate build, test, and release stages but normally stop at failure and leave diagnosis to engineers. DevOps research emphasizes delivery performance, feedback, and operational reliability [14]-[18]. These works motivate repeatable automation but do not by themselves provide a source-level repair loop."),
    P("Self-healing CI/CD and AIOps research studies feedback-loop automation, predictive reliability, infrastructure recovery, and AI-assisted DevOps [1]-[5]. LogSage specifically examines LLM-based CI/CD failure detection and remediation [13]. CICD Healing Agent differs by focusing on a small, reproducible source-repair workflow whose candidate is accepted only after the repository's tests pass."),
    P("Automated program repair includes template-based repair such as TBar [6], neural execution-guided repair [7], LLM-generated repair [8], conversational repair [9], and repository-level agents such as AutoCodeRover, SWE-agent, Agentless, RepairAgent, RepoCoder, and ChatRepair [10]-[12], [19]-[22]. These studies establish the value of execution feedback and repository context. The present system complements them with trust-gated reuse: a validated repair can avoid a later model call."),
    P("Container and software-supply-chain work provides the operational basis for isolated execution [23], [24]. The research gap addressed here is the integration of these ideas into one explainable loop: clone, isolate, test, reduce logs, hash the error, reuse or generate a repair, validate, and deliver through a reviewable pull request."),
]

story += [P("III. SYSTEM ARCHITECTURE", "Section")]
story += [
    P("The deployed local architecture is intentionally small and explainable. The browser dashboard sends a request to FastAPI. The backend coordinates repository operations, test execution, error analysis, memory lookup, repair generation, validation, and GitHub delivery."),
    P("<b>Figure 1. Implemented CICD pipeline:</b><br/>Repository URL and configuration -> clone repository -> create repair branch -> build and run Docker test image -> capture pytest output -> reduce log noise -> parse error -> query SQLite memory -> cache hit or OpenRouter repair -> apply source -> rerun Docker tests -> commit -> push -> create pull request." , "CodeBlock"),
]
story.append(table([
    ["Subsystem", "Implemented responsibility"],
    ["Dashboard", "Single-screen pipeline view, repository/source-branch/target-file input, live returned logs, stage status, and result summary."],
    ["FastAPI backend", "Exposes /analyze, /fix-and-push, memory inspection endpoints, and coordinates the complete workflow."],
    ["Repository manager", "Clones public or authenticated GitHub repositories and creates a dedicated repair branch when a GitHub token is available."],
    ["Docker runner", "Builds a temporary Python 3.11 image, installs requirements, runs pytest, and returns stdout, stderr, exit code, and combined logs."],
    ["Log and error analysis", "Filters pytest output, extracts error type/message/file/line/test information, and creates a deterministic error hash."],
    ["Fix engine", "Checks validated memory first, then invokes OpenRouter and retries bounded repair attempts."],
    ["Persistence", "SQLite stores errors, fixes, compressed logs, occurrence counts, application counts, and success rates."],
    ["GitHub delivery", "Commits and pushes validated changes and optionally creates a pull request through the GitHub API."],
], [42*mm, 132*mm]))

story += [P("IV. CLOSED-LOOP WORKFLOW", "Section")]
story += [P("For a repository state S and a maximum attempt budget K, the system executes tests and receives output L. The log processor produces an actionable representation E and the analyzer derives an error hash h from the error type and normalized message. The memory lookup first searches for a fix associated with h. If a trusted fix exists, it is applied directly. Otherwise, OpenRouter receives the target path, source file, test output, and repair constraints and returns a complete corrected source file. The candidate is tested before it can be delivered."),
           P("The loop terminates when tests pass, when the attempt budget is exhausted, or when a required operation fails. On failure, the original target file is restored. A successful repair is recorded with its application count and success rate, providing evidence for future reuse."),
           P("<b>Figure 2. Runtime decision path:</b><br/>Initial Docker test -> failure parse -> exact error-hash lookup -> trusted fix available? -> yes: apply cached fixed_code and validate; no: call OpenRouter -> apply generated code -> validate -> record outcome -> retry or deliver.", "CodeBlock")]

story += [P("V. ERROR MEMORY AND VALIDATED FIXES", "Section")]
story += [
    P("The local implementation uses SQLite rather than the PostgreSQL or MongoDB variants described in earlier drafts. The database file is stored at <b>cicd/workspace/cicd_errors.db</b>, independent of the directory from which the server is started. The principal tables are errors, fixes, logs, and error_similarities."),
]
story.append(table([
    ["Table", "Important fields and purpose"],
    ["errors", "error_hash, error_type, error_message, stack_trace, repository URL, target file, occurrence count, timestamps."],
    ["fixes", "error_id, fixed_code, fix_method, source, ai_model, applied_count, success_rate, creation time."],
    ["logs", "Compressed execution output, summary, original size, compressed size, ratio, and related fix."],
    ["error_similarities", "Relationships between recorded errors with similarity score and match type."],
], [42*mm, 132*mm]))
story += [
    P("A fix is eligible for automatic cache reuse only when it has at least one recorded application and a success rate of at least 90 percent. During a cache hit, the Fix Engine returns the stored fixed_code with method <i>cache</i>; the backend writes that code to the target file and runs Docker tests. OpenRouter is not called for that attempt. During a memory miss, the fix is generated through OpenRouter, stored as an AI fix, applied, and then scored according to the validation result."),
    P("This distinction is important for governance: a generated candidate is not trusted merely because it is syntactically valid. It becomes reusable memory only after the system has observed successful validation. The dashboard log records markers such as [FIX] Method: cache, [MEMORY] Reused known successful fix, or [FIX] Method: ai."),
]

story += [P("VI. IMPLEMENTATION DETAILS", "Section")]
story += [P("<b>Repository and branches.</b> The user supplies a repository URL, source branch, and target file. The backend clones the selected source branch, creates a generated repair branch when GITHUB_TOKEN is configured, and never places credentials in the browser log. Public repositories can be cloned without a GitHub token; a token is needed for pushing and pull-request creation."),
           P("<b>Docker execution.</b> Docker is the default isolation boundary. The runner creates a temporary Dockerfile, copies the repository into a Python 3.11 image, installs requirements.txt when present, installs pytest, and executes the test suite. Build and test output are captured for diagnosis. This provides repeatability and protects the host from repository-specific dependency changes, although resource limits and repository trust still require operational controls."),
           P("<b>AI repair.</b> OpenRouter is called only for a cache miss or when a previous candidate fails. The prompt contains the target file, original source, pytest output, and constraints against hardcoding visible test values. The response is cleaned, parsed as Python, written to the target file, and validated by another Docker test run."),
           P("<b>Delivery.</b> After successful validation, the backend commits changes, pushes the repair branch using an authenticated Git operation, and calls the GitHub pull-request API. Without a GitHub token, local healing and validation remain possible, but push and pull-request stages are intentionally disabled."),
]

story += [P("VII. EVALUATION AND DEMONSTRATION", "Section")]
story += [P("The recommended demonstration uses a small Python repository with an intentionally incorrect function and a failing pytest assertion. The first run should show a memory miss, an OpenRouter repair, a passing validation run, and a stored fix. A second run with the same error should show a memory hit and the cache method without an OpenRouter request. The experiment should record initial and final test counts, elapsed time, attempt count, memory status, repair method, and delivery result."),
           P("The current bundled Docker example is a passing repository by default. To exercise the repair path, its source must be intentionally seeded with a defect while its test retains the correct expected behavior. Results should be reported from actual runs; placeholder success rates and speed claims should not be presented as measured facts."),
]
story.append(table([
    ["Metric", "Measurement procedure"],
    ["Memory hit rate", "Cached repair runs divided by all eligible repeated-error runs."],
    ["Repair success rate", "Runs whose post-repair Docker tests pass divided by repair attempts."],
    ["Mean attempts", "Average number of AI/cache applications per healed run."],
    ["Time to recovery", "Elapsed time from initial failed test to validated repair."],
    ["AI calls avoided", "Runs with cache method compared with all healed runs."],
    ["Delivery reliability", "Successful commits, pushes, and pull requests divided by validated repairs."],
], [55*mm, 119*mm]))

story += [P("VIII. LIMITATIONS, SECURITY, AND SCALE", "Section")]
story += [P("The current prototype is strongest for Python repositories with pytest-compatible tests. It does not yet poll arbitrary GitHub Actions workflows; it runs the cloned repository's tests directly in Docker. It also does not guarantee semantic correctness beyond the available tests, so pull-request review remains important. Error matching currently depends heavily on the extracted error type and message; different assertion text can produce a new memory entry even when the underlying bug is similar."),
           P("Docker is recommended for the demonstration because it standardizes dependencies and isolates execution. A no-Docker mode could be added for trusted repositories and faster local development, but it would execute untrusted code on the host and could produce environment-dependent results. It should therefore be an explicit opt-in mode with clear security warnings, not the default."),
           P("Large repositories are possible but the current implementation copies the complete repository into the build context and sends the target source plus test output to the model. For large projects, build context exclusions, dependency caching, maximum repository size, log truncation, target-file limits, and model context limits should be enforced. SQLite is suitable for a local prototype; concurrent jobs and large-scale deployment require a server database, job queue, artifact storage, authentication, and resource quotas."),
           P("Secrets must remain in environment variables or a secret manager. GitHub and OpenRouter credentials should be rotated if exposed, and should never be printed in logs, embedded in frontend code, or committed to version control."),
]

story += [P("IX. CONCLUSION AND FUTURE WORK", "Section")]
story += [P("CICD Healing Agent demonstrates a practical self-healing loop for Python CI failures: clone, test in Docker, reduce logs, analyze, consult validated memory, generate or reuse a repair, validate, and deliver through Git. The revised implementation is more concrete than the original prototype description because it documents the actual FastAPI, SQLite, Docker, OpenRouter, and GitHub behavior currently present in the project."),
           P("Future work includes GitHub Actions workflow polling, broader language runners, patch-based rather than complete-file AI output, stronger normalized and semantic error matching, repository and job resource limits, authenticated multi-user deployment, benchmark evaluation, and mandatory human review with risk scoring."),
]

story += [P("REFERENCES", "Section")]
references = [
    "[1] M. Fowler, Continuous Integration, martinfowler.com, 2006. Available: https://martinfowler.com/articles/continuousIntegration.html.",
    "[2] P. M. Duvall, S. Matyas, and A. Glover, Continuous Integration: Improving Software Quality and Reducing Risk, Addison-Wesley, 2007.",
    "[3] E. Vasilescu, B. Yu, V. Filkov, and A. Serebrenik, Quality and productivity outcomes relating to continuous integration in GitHub, in Proceedings of the 2015 10th Joint Meeting on Foundations of Software Engineering (ESEC/FSE), pp. 805-816, 2015, doi: 10.1145/2786805.2786850.",
    "[4] M. Hilton et al., Usage, costs, and benefits of continuous integration in open-source projects, in Proceedings of the 31st IEEE/ACM International Conference on Automated Software Engineering (ASE), pp. 426-437, 2016, doi: 10.1109/ASE.2016.7582795.",
    "[5] B. Fitzgerald and K.-J. Stol, Continuous software engineering: A roadmap and agenda, Journal of Systems and Software, vol. 123, pp. 176-189, 2017, doi: 10.1016/j.jss.2015.06.063.",
    "[6] K. Liu et al., TBar: Revisiting template-based automated program repair, ISSTA, 2019.",
    "[7] H. Ye, M. Martinez, and M. Monperrus, Neural program repair with execution-based backpropagation, ICSE, 2022.",
    "[8] Z. Fan et al., Automated repair of programs from large language models, ICSE, 2023.",
    "[9] C. S. Xia and L. Zhang, Automated program repair via conversation, ISSTA, 2024.",
    "[10] Y. Zhang et al., AutoCodeRover: Autonomous program improvement, arXiv:2404.05427, 2024.",
    "[11] J. Yang et al., SWE-agent: Agent-computer interfaces enable automated software engineering, NeurIPS, 2024.",
    "[12] C. S. Xia et al., Agentless: Demystifying LLM-based software engineering agents, arXiv:2407.01489, 2024.",
    "[13] W. Xu et al., LogSage: An LLM-based framework for CI/CD failure detection and remediation with industrial validation, arXiv:2506.03691, 2025.",
    "[14] J. Humble and D. Farley, Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation, Addison-Wesley, 2010.",
    "[15] G. Kim, J. Humble, P. Debois, and J. Willis, The DevOps Handbook, IT Revolution Press, 2016.",
    "[16] N. Forsgren, J. Humble, and G. Kim, Accelerate: The Science of Lean Software and DevOps, IT Revolution Press, 2018.",
    "[17] L. Chen, Continuous delivery: Huge benefits, but challenges too, IEEE Software, vol. 32, no. 2, pp. 50-54, 2015, doi: 10.1109/MS.2015.27.",
    "[18] C. Ebert, G. Gallardo, J. Hernantes, and N. Serrano, DevOps, IEEE Software, vol. 33, no. 3, pp. 94-100, 2016, doi: 10.1109/MS.2016.68.",
    "[19] M. Monperrus, The Living Review on Software Bug and Fixes, arXiv:1801.06313, 2018.",
    "[20] J. Durieux et al., Astor: A program repair library for Java, in Proceedings of the 28th ACM SIGSOFT International Symposium on Software Testing and Analysis (ISSTA), pp. 441-444, 2019, doi: 10.1145/3293882.3330560.",
    "[21] R. Just, D. Jalali, and M. D. Ernst, Defects4J: A database of existing faults to enable controlled testing studies for Java programs, in Proceedings of the 2014 International Symposium on Software Testing and Analysis (ISSTA), pp. 437-440, 2014, doi: 10.1145/2610384.2628055.",
    "[22] M. Martinez and M. Monperrus, Astor: Exploring the design space of generate-and-validate program repair beyond GenProg, Journal of Systems and Software, vol. 151, pp. 272-290, 2019, doi: 10.1016/j.jss.2019.02.001.",
    "[23] D. Merkel, Docker: Lightweight Linux containers for consistent development and deployment, Linux Journal, vol. 2014, no. 239, 2014.",
    "[24] W. Felter, A. Ferreira, R. Rajamony, and J. Rubio, An updated performance comparison of virtual machines and Linux containers, in 2015 IEEE International Symposium on Performance Analysis of Systems and Software, pp. 171-172, 2015, doi: 10.1109/ISPASS.2015.7095802.",
]
for reference in references:
    story.append(P(reference, "Small"))

PaperDoc(OUTPUT).build(story)
print(OUTPUT)
