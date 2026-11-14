# SPEC: HackPrinceton Fall '26

Working name, rename later.

## One line
A catering coordinator for a real Nassau Street restaurant (Jammin' Crêpes first, Ficus as the backup) that keeps the quote, kitchen sheet and delivery plan in sync when a customer changes the order over text.

## Hook
"The order changed. The kitchen sheet didn't."
Replace with the manager's own words and number after the Saturday visit ("X of the last 10 catering orders changed after the quote").

## Users
1. **Primary: the restaurant manager.** Approves quotes and changes, sees what needs attention today.
2. **Secondary: the organizer** (a club, a company, an event planner) who texts the order in.

## Demo (2 min)
1. Hook, one sentence.
2. The organizer texts: lunch for 35, Tuesday, $700, 5 vegetarian. The agent asks for the missing address and serving time.
3. The agent checks the real menu and ordering rules, builds a quote, and the manager approves it. The kitchen sheet is created.
4. **A judge texts the change live:** "make it 50, ten vegetarian, same budget."
5. The agent works out what is affected (quote, kitchen sheet, delivery) and shows a before/after diff. The manager approves it and everything updates.
6. The manager corrects it: "deliveries to that building need extra time for the loading dock." Save it as a rule (this event / this customer / this building).
7. A second, new order to the same building uses the rule automatically.
8. Close with the manager's real number.

## Pipeline (build only this)
text intake -> menu + rules check -> quote -> manager approval -> kitchen sheet -> change -> diff -> approve -> correction saved as a rule -> next order uses it

Cut for this weekend: recovery after restarts, the completion stage, multiple agents, fancy deduplication.

## Data model
- **Customer:** contact, saved preferences.
- **Event:** date, address, serving time, headcount, dietary needs, status.
- **Quote:** line items, total, version, approved_by, approved_version. A change makes the old approval invalid.
- **ProductionJob:** quantities, prep deadline, delivery notes. Always built from the current approved quote.
- **Commitment:** what was promised, by whom, by when, and the message it came from.
- **Rule:** text, scope (event / customer / location), version, approved_by.

## Stack
- **Photon:** texting in and out (confirm iMessage works for the demo) [check]
- **LangChain deepagents:** the coordinator agent, with human approval
- **Amazon Bedrock:** the model
- **MongoDB Atlas:** orders, quote versions, commitments, rules, action log
- **Web UI:** "What needs attention today?" cards with approve/edit, plus the diff view

## Hard rules
- Prices, totals, headcount math and state changes happen in plain code. The model picks and explains actions, it never does the math.
- Use the real public menu and ordering rules. Anything simulated is labeled as simulated, in the demo and on the Devpost.
- No keys in git. Use `.env` (see `.env.example`).
- Customer messages can request changes. Only the manager can change prices or rules.

## Who builds what
| Person | Owns |
|---|---|
| Candy | Web UI: today's cards, diff view, approval flow |
| Christian | Agent + backend (when he lands) |
| Jayden | Menu, ordering rules, data model, MongoDB |
| Sarah | Producer: client visit, Peri evidence, pitch, Devpost, video |

## Peri evidence to collect
Business name, the manager's name and role (with permission), visit notes, a photo, and what changed in the build because of their feedback.

## Deadlines
- Video recorded Saturday night.
- Devpost submitted before midnight Saturday. Repo public.
