const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  ImageRun, PageBreak, Footer, PageNumber, LevelFormat, convertInchesToTwip,
} = require("docx");

const IMG = path.join(__dirname, "img");
const TEAL = "0D5C63";
const TEAL_PALE = "E4F0F0";
const AMBER = "B8690B";
const RED = "A8322A";
const GREEN = "1F7A44";
const INK = "1F2937";
const GREY = "5A6673";
const GREY_PALE = "F1F5F9";
const LINE = "CBD5E1";

const FONT = "Calibri";
const CONTENT_W = 9314; // dxa: A4 (11906) minus 0.9in margins each side

/** Column widths as fractions of CONTENT_W, guaranteed to sum exactly. */
function cols(...fracs) {
  const total = fracs.reduce((a, b) => a + b, 0);
  const w = fracs.map((f) => Math.floor((f / total) * CONTENT_W));
  w[w.length - 1] += CONTENT_W - w.reduce((a, b) => a + b, 0);
  return w;
}

// ---------------------------------------------------------------- helpers
function H1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 180 },
    children: [new TextRun({ text, font: FONT, size: 34, bold: true, color: TEAL })],
  });
}

function H2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, font: FONT, size: 26, bold: true, color: INK })],
  });
}

function P(text, opts = {}) {
  const { bold = false, size = 22, color = INK, after = 140, italics = false,
          align = AlignmentType.LEFT, before = 0 } = opts;
  return new Paragraph({
    alignment: align,
    spacing: { after, before, line: 300 },
    children: [new TextRun({ text, font: FONT, size, bold, color, italics })],
  });
}

// A paragraph made of mixed runs: [["plain "], ["bold", {bold:true}]]
function PR(runs, opts = {}) {
  const { after = 140, size = 22, align = AlignmentType.LEFT, before = 0 } = opts;
  return new Paragraph({
    alignment: align,
    spacing: { after, before, line: 300 },
    children: runs.map(([t, o = {}]) => new TextRun({
      text: t, font: FONT, size: o.size || size, bold: !!o.bold,
      italics: !!o.italics, color: o.color || INK,
    })),
  });
}

function bullet(text, opts = {}) {
  const { bold = false, color = INK } = opts;
  return new Paragraph({
    numbering: { reference: "dots", level: 0 },
    spacing: { after: 90, line: 300 },
    children: [new TextRun({ text, font: FONT, size: 22, bold, color })],
  });
}

function img(file, widthIn = 6.4) {
  const meta = {
    "01-problem.png": 0.5381, "02-bigpicture.png": 0.5885,
    "03-pillars.png": 0.4789, "04-journey.png": 0.4668,
    "05-safety.png": 0.5633, "06-warning.png": 0.4623,
    "07-residency.png": 0.4789, "08-plan.png": 0.3929,
  };
  const w = Math.round(widthIn * 96);
  const h = Math.round(w * meta[file]);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 160, after: 100 },
    children: [new ImageRun({
      type: "png",
      data: fs.readFileSync(path.join(IMG, file)),
      transformation: { width: w, height: h },
    })],
  });
}

function caption(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 260 },
    children: [new TextRun({ text, font: FONT, size: 17, italics: true, color: GREY })],
  });
}

function noBorders() {
  const n = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
  return { top: n, bottom: n, left: n, right: n };
}

function cell(text, o = {}) {
  const { w, bold = false, fill = null, color = INK, size = 20,
          align = AlignmentType.LEFT, span = 1 } = o;
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    columnSpan: span,
    shading: fill ? { type: ShadingType.CLEAR, fill, color: "auto" } : undefined,
    margins: { top: 90, bottom: 90, left: 120, right: 120 },
    children: [new Paragraph({
      alignment: align,
      spacing: { after: 0, line: 260 },
      children: [new TextRun({ text, font: FONT, size, bold, color })],
    })],
  });
}

/** rows: array of arrays of strings; widths must sum to CONTENT_W */
function table(widths, header, rows, opts = {}) {
  const { headerFill = TEAL, zebra = true, firstColBold = false } = opts;
  const trs = [];
  if (header) {
    trs.push(new TableRow({
      tableHeader: true,
      children: header.map((t, i) =>
        cell(t, { w: widths[i], bold: true, fill: headerFill, color: "FFFFFF", size: 20 })),
    }));
  }
  rows.forEach((r, ri) => {
    trs.push(new TableRow({
      children: r.map((t, i) => cell(t, {
        w: widths[i],
        bold: firstColBold && i === 0,
        fill: zebra && ri % 2 === 1 ? GREY_PALE : null,
      })),
    }));
  });
  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: {
      top:    { style: BorderStyle.SINGLE, size: 2, color: LINE },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: LINE },
      left:   { style: BorderStyle.SINGLE, size: 2, color: LINE },
      right:  { style: BorderStyle.SINGLE, size: 2, color: LINE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: LINE },
      insideVertical:   { style: BorderStyle.SINGLE, size: 2, color: LINE },
    },
    rows: trs,
  });
}

/** A single-cell coloured callout box. */
function callout(title, body, color = TEAL, fill = TEAL_PALE) {
  return new Table({
    columnWidths: [CONTENT_W],
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: {
      top:    { style: BorderStyle.SINGLE, size: 2, color: color },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: color },
      left:   { style: BorderStyle.SINGLE, size: 18, color: color },
      right:  { style: BorderStyle.SINGLE, size: 2, color: color },
      insideHorizontal: { style: BorderStyle.NONE, size: 0, color: "auto" },
      insideVertical:   { style: BorderStyle.NONE, size: 0, color: "auto" },
    },
    rows: [new TableRow({
      children: [new TableCell({
        width: { size: CONTENT_W, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill, color: "auto" },
        margins: { top: 160, bottom: 160, left: 200, right: 200 },
        children: [
          new Paragraph({
            spacing: { after: title && body ? 80 : 0, line: 290 },
            children: [new TextRun({ text: title, font: FONT, size: 22, bold: true, color })],
          }),
          ...(body ? [new Paragraph({
            spacing: { after: 0, line: 290 },
            children: [new TextRun({ text: body, font: FONT, size: 21, color: INK })],
          })] : []),
        ],
      })],
    })],
  });
}

const gap = (n = 160) => new Paragraph({ spacing: { after: n }, children: [] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// ---------------------------------------------------------------- cover
const cover = [
  gap(1400),
  new Paragraph({
    spacing: { after: 60 },
    children: [new TextRun({ text: "BRIEFING NOTE", font: FONT, size: 20,
      bold: true, color: GREY, characterSpacing: 60 })],
  }),
  new Paragraph({
    spacing: { after: 100 },
    children: [new TextRun({ text: "SawtAI", font: FONT, size: 76, bold: true, color: TEAL })],
  }),
  new Paragraph({
    spacing: { after: 340 },
    children: [new TextRun({
      text: "An AI platform that helps a government entity understand what the public is saying, reply to it properly, and see trouble coming.",
      font: FONT, size: 26, color: INK })],
  }),
  new Paragraph({
    border: { top: { style: BorderStyle.SINGLE, size: 12, color: TEAL, space: 8 } },
    spacing: { after: 260 },
    children: [],
  }),
  table(cols(26, 68), null, [
    ["Prepared for", "Executive leadership"],
    ["Purpose", "Decision on submission to the Sharjah Government Communication Award 2026"],
    ["Category", "Best Use of Artificial Intelligence in Government and Institutional Communication"],
    ["Submission deadline", "31 August 2026 — 29 days from today"],
    ["Date of this note", "2 August 2026"],
    ["Status", "Design agreed; build starts 3 August"],
  ], { zebra: true, firstColBold: true }),
  gap(400),
  callout(
    "What this note is for",
    "It explains, without technical detail, what we are building, why it is different from the AI tools you have seen before, what it will cost, and the three decisions we need from you this week.",
    TEAL, TEAL_PALE),
  pageBreak(),
];

// ---------------------------------------------------------------- section 1
const s1 = [
  H1("1.  The short version"),
  P("Government entities receive an enormous amount of public communication — social media posts, complaint forms, emails, surveys, calls. Almost all of it in Arabic, much of it in Gulf dialect, plenty of it mixed with English. Today a small team reads whatever it can get to, summarises it weekly, and finds out about serious problems at roughly the same time as the newspapers do.",
    { after: 180 }),
  P("SawtAI changes three things:", { bold: true, after: 140 }),
  bullet("It reads all of it, not a sample — and understands Arabic properly, including dialect."),
  bullet("It writes the official reply for the officer, using only the entity's own approved documents, and shows the source of every sentence."),
  bullet("It watches how fast an issue is growing and warns the team hours or days before it becomes a public problem."),
  gap(120),
  P("A person still decides and approves everything. The system never publishes anything on its own.",
    { bold: true, after: 240 }),

  H2("At a glance"),
  table(cols(27, 67), null, [
    ["What it is", "One platform doing three jobs: understand the public, draft the response, warn about crises."],
    ["Who uses it", "Communication officers, department heads, and a crisis lead. Not the public."],
    ["Language", "Arabic first — Modern Standard and Gulf dialect — with English alongside. The screens read right-to-left, as they should."],
    ["Biggest safeguard", "It refuses to write anything the entity's own approved documents do not support, and says so."],
    ["Where data sits", "Citizen messages never leave our control. There is also a setting where nothing leaves at all."],
    ["Cost to build the prototype", "Around AED 550–650 (US$150–175) in services, plus our own time. No new hardware."],
    ["What exists on 31 August", "A working prototype on a realistic test dataset, measured results, and a three-minute film."],
  ], { zebra: true, firstColBold: true }),
  gap(300),
  callout("The one thing to remember",
    "Most AI demonstrations show a system that always produces an answer. Ours is built to say “I cannot support that” and stop. In government communication, that is the more valuable behaviour — and it is the thing judges have not seen before.",
    AMBER, "FDF1DE"),
  pageBreak(),
];

// ---------------------------------------------------------------- section 2
const s2 = [
  H1("2.  The problem we are solving"),
  P("The volume of public communication reaching an entity has grown far faster than the team reading it. The result is not that the entity ignores the public — it is that it can only ever respond to the fraction somebody happened to see, and always after the fact."),
  img("01-problem.png"),
  caption("How public feedback is handled today"),
  gap(80),
  H2("Three specific costs of working this way"),
  table(cols(24, 70), ["", "What it costs the entity"], [
    ["Blind spots", "Decisions are made on a sample nobody chose deliberately. A rising complaint about one district can stay invisible for weeks."],
    ["Slow, uneven replies", "Two officers answering the same complaint may say different things. Drafting an official reply takes hours, and quality depends on who is on shift."],
    ["Surprises", "The first sign of a serious issue is usually a journalist calling. By then the entity is responding, not communicating."],
  ], { firstColBold: true }),
  pageBreak(),
];

// ---------------------------------------------------------------- section 3
const s3 = [
  H1("3.  What SawtAI does"),
  P("Everything the public sends arrives in one place. The system reads it, sorts it, and gives the communication team a live picture instead of a weekly one. When the team needs to respond, it drafts the response. When something is escalating, it says so."),
  img("02-bigpicture.png"),
  caption("Public feedback comes in; an approved, on-message response goes out"),
  gap(160),
  H2("The three jobs, in more detail"),
  img("03-pillars.png"),
  caption("What each capability does, and what it means for the entity"),
  pageBreak(),
];

// ---------------------------------------------------------------- section 4
const s4 = [
  H1("4.  How it works in practice"),
  P("The clearest way to explain the platform is to follow a single complaint through it."),
  img("04-journey.png"),
  caption("A resident's complaint, from arrival to published reply — about nine minutes"),
  gap(120),
  P("Two things are worth noticing in that sequence.", { bold: true, after: 140 }),
  PR([["First, personal details are removed automatically, within a second of arrival — ", {}],
      ["before anything is stored at all", { bold: true }],
      [". The system does not hold the resident's phone number or ID; it holds the complaint. Nobody, including our own administrators, can look up “everything this citizen has ever said”, because the platform is deliberately built without that ability.", {}]]),
  PR([["Second, the officer is still writing and the manager is still approving. ", {}],
      ["The system removes the waiting, not the judgement.", { bold: true }],
      [" What takes one to two working days today takes minutes — and the reply is consistent with what the entity has already published elsewhere.", {}]]),
  pageBreak(),
];

// ---------------------------------------------------------------- section 5
const s5 = [
  H1("5.  Can it be trusted to write on our behalf?"),
  P("This is the right question, and it is the question the whole design is built around. The risk with AI writing tools is well known: they produce fluent, confident text that sounds correct and is not. For a government entity, publishing one invented commitment or one wrong date is a serious incident."),
  P("SawtAI is built so that cannot happen quietly. There are three barriers, and a fourth that is simply a person.", { bold: true }),
  img("05-safety.png"),
  caption("The drafting process — and the refusal that happens when there is no approved source"),
  gap(160),
  H2("What that means in plain terms"),
  table(cols(26, 68), null, [
    ["It cannot invent policy", "It may only draw on documents the entity has already approved. If we have not published a position on something, it will not produce one."],
    ["It shows its working", "Every sentence in a draft is marked with the document and paragraph it came from. A manager can check any claim in seconds."],
    ["It refuses", "When there is no approved source, it stops, explains why, and names the document that would need to exist. It does not guess."],
    ["It cannot promise things", "It is specifically blocked from writing compensation offers, deadlines, admissions of liability, or blame directed at another body."],
    ["A person always approves", "Nothing can be published without a named manager approving it, and that approval is recorded permanently. The person who wrote a draft cannot approve their own."],
    ["Hostile messages cannot steer it", "Some people will send messages designed to trick the system into writing something damaging. Those messages are treated as evidence to read, never as instructions to follow — and are flagged for the team."],
  ], { zebra: true, firstColBold: true }),
  gap(280),
  callout("Every action leaves a permanent record",
    "Who read what, who drafted what, who approved it, and which documents it was based on — all recorded and un-editable. If we are ever asked to explain why the entity published a particular statement, we can answer completely, in about a minute.",
    GREEN, "E7F4EC"),
  pageBreak(),
];

// ---------------------------------------------------------------- section 6
const s6 = [
  H1("6.  Seeing a problem before it becomes a crisis"),
  P("The third capability is the one most people find hardest to picture, so here is a real shape of it. Rather than waiting for an issue to trend, the system tracks how quickly a topic is growing, how quickly the mood around it is souring, how many different people are involved, and whether it is something new."),
  img("06-warning.png"),
  caption("A real pattern from our test data: the alert comes three days before the public peak"),
  gap(140),
  P("The team is not told “there will be a crisis”. They are told: this issue is behaving like one that escalates, here are the specific reasons, here are the messages behind it, and here is the response plan for this type of problem. They then decide.",
    { after: 200 }),
  callout("An honest note on this capability",
    "Predicting escalation well requires history of past escalations, and no entity has that data labelled today. What we are building is a well-designed early-warning score — transparent about why it fired — plus the mechanism that collects the history a stronger model would need. We would rather present that accurately than overstate it. Competitors are likely to claim more; we can defend our version under questioning.",
    AMBER, "FDF1DE"),
  pageBreak(),
];

// ---------------------------------------------------------------- section 7
const s7 = [
  H1("7.  Where the data lives"),
  P("For any government entity this is the question that decides whether a system can be adopted at all, so it was designed first rather than added afterwards."),
  img("07-residency.png"),
  caption("What stays inside our control, and the only thing that ever goes out"),
  gap(140),
  H2("Two settings, and the entity chooses"),
  table(cols(24, 35, 35), ["", "Standard setting", "Fully self-contained"], [
    ["Citizen messages", "Never leave. Processed entirely on our own equipment.", "Never leave."],
    ["Our approved documents", "Used by an external writing service when drafting a reply.", "Never leave. Everything runs on our own equipment."],
    ["Quality of Arabic writing", "Highest available.", "Very good, slightly below the standard setting."],
    ["Cost", "Lower.", "Higher — needs more of our own hardware."],
  ], { firstColBold: true }),
  gap(220),
  P("We will demonstrate both settings working. That matters: it means the answer to “can this run entirely inside government infrastructure?” is something we can show rather than promise.",
    { bold: true }),
  pageBreak(),
];

// ---------------------------------------------------------------- section 8
const s8 = [
  H1("8.  What we will have by 31 August"),
  P("There are 29 days to the deadline. The plan is built backwards from it, and each week ends with something that can actually be shown."),
  img("08-plan.png"),
  caption("Four weeks, with a hard stop on building a week before the deadline"),
  gap(140),
  H2("Prototype now, product later — the honest split"),
  P("It is important that this document does not blur the two. What we submit in August is a working demonstration on realistic test data. It is not yet something that should touch live citizen information."),
  table(cols(30, 32, 32), ["", "In the August prototype", "Needed before a real pilot"], [
    ["The three capabilities", "All working", "Tuning against that entity's own data"],
    ["The data it runs on", "A realistic test dataset we generate ourselves", "Real data from a partner entity"],
    ["Sign-in and permissions", "Basic, working", "Connected to the entity's own staff login"],
    ["Security hardening", "Not complete — appropriate for a demonstration", "Full security review and accreditation"],
    ["Running it live", "On our own machine", "Hosted properly, backed up, monitored"],
  ], { firstColBold: true }),
  gap(240),
  callout("Why the test dataset matters, and how we handle it",
    "No entity has given us data, so we generate a realistic Arabic dataset ourselves. Every performance figure we publish will be clearly labelled as measured on that dataset. Overstating it would be the fastest way to lose credibility with a technical judge — and the system is built so real data can be swapped in without changing anything.",
    GREY, GREY_PALE),
  pageBreak(),
];

// ---------------------------------------------------------------- section 9
const s9 = [
  H1("9.  What it costs"),
  H2("To build and submit the prototype"),
  table(cols(42, 26, 26), ["", "US$", "AED (approx.)"], [
    ["Building the Arabic test dataset", "15 – 25", "55 – 92"],
    ["AI writing service during development and the demo", "20 – 30", "73 – 110"],
    ["Testing and measurement", "10 – 15", "37 – 55"],
    ["A small server so judges can try it online", "40 – 60", "147 – 220"],
    ["Domain name and contingency", "50", "184"],
    ["Total", "125 – 170", "460 – 625"],
  ], { firstColBold: true }),
  P("No new hardware is required — the work runs on equipment we already have. The main cost is our own time: roughly 250–350 hours across the team over four weeks.",
    { after: 240, before: 120 }),

  H2("To run it properly for one entity, afterwards"),
  P("This is the number that matters if this becomes real. For an entity receiving around half a million messages a month:"),
  table(cols(42, 26, 26), ["", "Per month, US$", "Per month, AED"], [
    ["Standard setting", "1,700 – 2,050", "6,250 – 7,530"],
    ["Fully self-contained setting", "2,400 – 2,700", "8,820 – 9,920"],
    ["One-off setup, integration and security accreditation", "25,000 – 60,000", "92,000 – 220,000"],
  ], { firstColBold: true }),
  gap(220),
  callout("The number worth quoting",
    "At that volume the platform costs a little under two fils per message handled — because the expensive part runs on our own equipment rather than being billed per use. That is the figure that makes this affordable at government scale.",
    TEAL, TEAL_PALE),
  pageBreak(),
];

// ---------------------------------------------------------------- section 10
const s10 = [
  H1("10.  The risks, stated plainly"),
  P("These are the things most likely to go wrong, and what we are doing about each. They are listed in the order we worry about them."),
  table(cols(27, 33, 33), ["Risk", "Why it matters", "What we are doing"], [
    ["Four weeks is not much time",
     "Missing the deadline means no submission at all.",
     "The scope is agreed in advance, and we have written down exactly what gets dropped first if we fall behind. All building stops a week early."],
    ["Nobody on the team can judge Arabic writing critically",
     "This is an Arabic-first platform. One awkward sentence and a judge discounts everything else.",
     "We need a confident Arabic reviewer for roughly eight hours across three fixed dates. This is the first thing to sort out this week."],
    ["No entity partner",
     "Awards of this kind favour entries already working inside a real entity.",
     "We are pursuing a letter of interest in parallel. Even one paragraph changes how the submission is read."],
    ["Our test data is not real data",
     "Judges may discount results measured on data we generated.",
     "We declare it openly on every figure and show how real data would be swapped in. Being straight about this earns more than it costs."],
    ["The early-warning capability under-delivers",
     "It is the hardest of the three to prove convincingly.",
     "We have a simpler, transparent version as the guaranteed outcome, and a check point mid-August to decide."],
  ], { firstColBold: true }),
  pageBreak(),
];

// ---------------------------------------------------------------- section 11
const s11 = [
  H1("11.  What we need from you"),
  P("Three things, none of them expensive.", { after: 220 }),

  callout("1.  Approval of the budget",
    "Around AED 650 in services for the prototype. No hardware purchase, no new licences, no commitment beyond August.",
    TEAL, TEAL_PALE),
  gap(180),
  callout("2.  An introduction to one Sharjah entity — this week",
    "This is the highest-value thing anyone can do for this project, and it is worth more than any amount of additional engineering. Even an expression of interest on entity letterhead materially changes how the submission is read. If you can open one door, please open it before Thursday.",
    AMBER, "FDF1DE"),
  gap(180),
  callout("3.  An Arabic reviewer for about eight hours",
    "Someone who writes Arabic confidently and can tell us honestly whether the system's output sounds like a government entity or like a translation. Three sessions: 6 August, 21 August, 28 August.",
    GREEN, "E7F4EC"),
  gap(340),

  H2("What happens next"),
  table(cols(22, 72), null, [
    ["This week", "Building starts 3 August. We come back to you on 14 August with the working dashboard."],
    ["Mid-August", "Second review, 21 August — drafting and early warning demonstrated."],
    ["End of August", "Final review 28 August, submission 29–30 August."],
    ["After that", "If the entry advances, or an entity shows interest, we move to a pilot. That is a separate decision and a separate budget."],
  ], { zebra: true, firstColBold: true }),
  gap(400),
  P("A full technical architecture document exists alongside this note, covering the system design, data handling, security model and delivery plan in detail. It is available on request.",
    { italics: true, color: GREY, size: 20 }),
];

// ---------------------------------------------------------------- document
const doc = new Document({
  creator: "SawtAI project team",
  title: "SawtAI — Briefing Note",
  description: "Executive briefing on the SawtAI government communication intelligence platform",
  numbering: {
    config: [{
      reference: "dots",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 460, hanging: 240 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: FONT, size: 22, color: INK } },
    },
  },
  sections: [{
    properties: {
      page: {
        margin: {
          top: convertInchesToTwip(0.9), bottom: convertInchesToTwip(0.9),
          left: convertInchesToTwip(0.9), right: convertInchesToTwip(0.9),
        },
      },
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 120 },
          children: [
            new TextRun({ text: "SawtAI  ·  Briefing note  ·  2 August 2026  ·  ",
              font: FONT, size: 16, color: GREY }),
            new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: GREY }),
          ],
        })],
      }),
    },
    children: [
      ...cover, ...s1, ...s2, ...s3, ...s4, ...s5,
      ...s6, ...s7, ...s8, ...s9, ...s10, ...s11,
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "..", "SawtAI-Briefing-Note.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out, (buf.length / 1024).toFixed(0) + " KB");
});
