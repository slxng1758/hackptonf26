# Overall: project idea, design and target prizes

We are making a project where we have agent simulations to react to our product, i.e. decide to buy, not buy, file a complaint, etc. AI agents with customer personas test a small business's decisions before it makes them, then measure their own accuracy against real results and improve from them. We care about their reaction, feelings, thoughts and after-actions about the product.

We must use LangChain deepagents. Ensure to use many functionalities of LangChain deepagents that are offered that fit our use case, i.e. subagents, sandbox, evals.

## How a human user puts in the product they want to test and the agent personas they want to run
Helper agent to simulate the product in a way that the agents understand what they are interacting with:
- Upload the product description
- Provide any context about the product, e.g. this is a new improvement from our previous version, or we changed X about the product
- Can choose to test the product in different world simulations/contexts, e.g. agents using a surgical mask product during COVID vs pre-COVID

## Features
- Agents reason about how many different user/customer profiles there are and create the appropriate number of agents with unique personas to participate in the simulation
- Include the following personas when suitable:
  - Price-sensitive vs quality-care buyer
  - Cares about brand vs functionality
  - New user: navigating the product for the first time
  - Skeptic: finds critiques in the product
  - Agreer: very enthusiastic about the product
- Agents evolve over time based on new customer information and their experiences, creating a feedback loop that evolves their personas

## Agent design

| deepagents feature | Our use |
|---|---|
| Main agent + planning | Orchestrator plans the run: segment the market → spawn personas → run scenarios → aggregate |
| Subagents | Product-briefing agent (the "helper"), market-segmentation agent, N persona agents, analyst/critic agent |
| Virtual filesystem | Each persona has a file like `personas/<id>.md` that it rewrites as it evolves. You get a visible history of how each persona changed. |
| Long-term memory (store backend) | Personas persist across runs, so the feedback loop is real |
| Sandbox | Personas actually use something: click through a landing page, run a pricing calculator, try a prototype. Much better than reading a description. |
| Human-in-the-loop interrupts | The business owner approves the generated personas before the run |
| LangSmith evals | Score predicted vs actual sentiment, rating and purchase intent. This is the accuracy number. |

## The influencer part
After the personas try the product, they post about it the way people do on social media. Then they see each other's posts and decide whether to reply, repost or ignore. That gives you a small network of who reacted to whom.

An "influencer" is the persona whose posts spread the furthest: the one others replied to or reposted most. It's measured with a standard network score (PageRank, the idea Google uses to rank pages).

Why it matters to a business: the average rating doesn't tell you which opinion will spread. In the example data, the skeptic is only 10% of customers, but their "shrinks in the dryer" post got picked up by two other groups. The useful insight is "this one complaint will spread by word of mouth, so fix it first (print 'air dry' on the label)." It's also what the Arlequin social-media track asks for: analyzing what people say together with who's connected to whom.

## Testing, evals and results
See [PLAN.md](PLAN.md) and [CONTRACT.md](CONTRACT.md).

---

# Target tracks and prizes

## Main track: Business & Enterprise
This category focuses on projects that enhance the efficiency of financial tools or streamline business operations. Examples include fintech tools for startups, B2B billing systems, analytics dashboards, cybersecurity solutions, and privacy-focused applications.

## MLH prizes (aim for as many as possible)

### [MLH] Best Use of Gemini API
1 winner · MLH Swag Kits

It's time to push the boundaries of what's possible with AI using Google Gemini. Check out the Gemini API to build AI-powered apps that make your friends say WHOA. So, what can Gemini do for your hackathon project?
- Understand language like a human and build a chatbot that gives personalized advice
- Analyze info like a supercomputer and create an app that summarizes complex research papers
- Generate creative content like code, scripts, music, and more

Think of the possibilities… what will you build with the Google Gemini API this weekend?

### [MLH] Best Use of Solana
1 winner · Unruggable Hardware Wallets

The world of development is evolving fast and Solana is leading the charge with a network built to handle all of your infrastructure needs. Forget high fees and slow confirmations, it's time to build applications that are fast, efficient, and scalable.

Harness Solana's core advantages like blazing fast execution and near-zero transaction costs to make your hackathon ideas become real world projects. With Solana, the possibilities are endless.
- Create a game, social app, or consumer product that relies on instant, high-frequency transactions.
- Design a sophisticated trading, lending, or decentralized exchange (DEX).
- Build a prototype for supply chain, identity, or payments that can handle massive, real-world volume.

Show us how you can innovate with Solana for a chance to win Unruggable Hardware Wallets for you and each member of your team!

### [MLH] Best Use of Tiger Data
1 winner · Stream Deck Mini

Building high-performance apps under hackathon deadlines shouldn't mean spending half your weekend configuring complex databases or learning obscure query languages. Tiger Data extends PostgreSQL to give student developers an ultra-fast foundation for real-time data, time-series metrics, and complex analytics.

Why build with Tiger Data this weekend?
- Standard SQL Power: Query massive datasets instantly using the SQL you already know, with no complex NoSQL aggregation pipelines required.
- Unified Data Stack: Store relational user profiles and high-frequency metric streams side-by-side in a single database.
- Instant Dashboards: Serve lag-free, real-time frontend charts using pre-computed Continuous Aggregates.
- 90%+ Data Compression: Store millions of events on free-tier cloud instances without running out of disk space.

Whether you're building real-time IoT monitoring, AI-driven analytics dashboards, or financial prediction engines, show us how Tiger Data powers your project. The team that demonstrates the most innovative, impactful, and performance-driven use of Tiger Data will take home some great prizes!

### [MLH] Best Use of Vultr
1 winner · Assorted Prizes

Vultr empowers hackers to bring their high-performance projects to life instantly; providing everything from the speed of one-click deployment and scalable cloud compute, to specialized Vultr Cloud GPUs that can power AI-driven applications. We want you to push the limits of what can be built when infrastructure is no longer the bottleneck!

Sign up for a Vultr account today and claim your free cloud credits! Take your next hack to the cloud with Vultr for a chance to win some awesome prizes for you and your team!

### [MLH] DEV Writing Challenge
1 winner · $100

Give your project another chance to shine! Your hackathon may end after the weekend, but your project story is just getting started. Publish what you built on DEV and help other developers learn from your process.

Each month, the DEV editorial team will select at least one favorite project. Additional projects may be selected depending on submission volume. Selections consider technical substance, originality, clear storytelling, and community popularity. Great work deserves an audience, so make your post useful, memorable, and easy to share.

### [MLH] Best Use of MongoDB Atlas
1 winner · M5Stack IoT Kit

MongoDB Atlas takes the leading modern database and makes it accessible in the cloud! Get started with a $50 credit for students or sign up for the Atlas free forever tier (no credit card required). Along with a suite of services and functionalities, you'll have everything you need to manage all of your data, and you can get a headstart with free resources from MongoDB University! Build a hack using MongoDB Atlas for a chance to win a M5Stack IoT Kit for you and each member of your group.

### [MLH] Best Domain Name from GoDaddy Registry
1 winner · Digital Gift Card

GoDaddy Registry is giving you everything you need to be the best hacker no matter where you are. Register your domain name with GoDaddy Registry for a chance to win some amazing prizes!

## Special tracks

### Best Practical AI Innovation, by Amazon (AIMING FOR THIS, in the most obvious way)
Build AI that solves a real problem for real people. Create AI-powered tools that go beyond demos: applications that reason, plan, take action, and adapt. Whether you're tackling healthcare, sustainability, accessibility, finance, education, logistics, or something entirely new, show us AI that someone would actually want to use every day.

Key focus areas:
- Agentic Behavior: Build AI that can reason, plan, and take multi-step actions
- Real-World Impact: Solve a problem that matters to real users, not just a demo
- Adaptive Intelligence: Learn from context, feedback, or user preferences
- User-Friendly Design: Make powerful AI feel simple and intuitive
- Creative Innovation: Surprise us with unexpected approaches and fresh ideas

Project ideas (examples):
- A conversational agent that helps users compare products, read reviews, and make purchase decisions through natural dialogue
- A logistics or delivery optimization tool that uses real-time data to route, schedule, or predict delays
- An accessibility tool that uses voice, vision, or gesture to help underserved users navigate technology
- A sustainability platform that turns real-world data (satellite, sensor, public records) into actionable insights
- An agentic AI sandbox or learning environment where AI collaborates with you interactively
- A personal finance or trading tool that monitors patterns, predicts risks, and coaches better decisions
- A group coordination agent that assigns tasks, tracks progress, and nudges teammates on deadlines
- A creative AI workflow that turns raw inputs into polished content (music, video, writing, design)
- An AI layer on top of existing platforms (messaging, scheduling, browsing) that adds intelligent automation
- A multi-agent system that researches and compares options across a domain (housing, courses, jobs, travel, energy)

Evaluation criteria:
- Creativity (25%): Is the idea original? Does it approach the problem in a surprising or clever way?
- Usefulness (25%): Does it solve a real problem someone would actually care about?
- Technical Implementation (25%): Is it well-built, reliable, and technically sound?
- User Experience (25%): Is it intuitive, polished, and something you'd want to use again?

Project must include: working prototype/demo; clear use case and target user; basic documentation; presentation/pitch.

Can use any combination of: open source AI tools, libraries, and frameworks; API services (LLM providers, search, data, vision, speech, etc.); custom models or fine-tuned systems; agentic frameworks and tool-use integrations; existing platforms and infrastructure.

Prizes (Amazon Gift Cards): 1st $125 per person, 2nd $75 per person, 3rd $50 per person (up to 4 team members).

### Forward Deployed Challenge, by Peri (AIMING FOR THIS)
Forward deployed engineers go on-site with businesses, learn how they actually operate, find where their workflows break down, and build solutions around real needs. This track asks teams to do the same. Build a project for any HackPrinceton track that solves a real problem for a real business you consulted during the hackathon: a local shop, a family business, a restaurant, a startup. The ideal entry starts with walking into the laundromat down the street, learning how they run, and building what they actually need. Student organizations and clubs also qualify.

**Eligibility:** Submissions must include the name of the business, the name and role of the person consulted, and one piece of supporting evidence (a screenshot of the conversation, a photo, a short video, or a direct quote).

Criteria:
- Real-world need: how clearly the project addresses a problem the business actually has.
- Usability: whether the business could realistically adopt the solution immediately.
- Execution: how complete and functional the project is end to end.

Judged by Peri, co-founded by two former Palantir forward deployed engineers. 1st to 3rd place: the top three teams will be introduced directly to the hiring teams at Peri's partner companies for a chance to interview: Cognition, Edra, Ephemeral, Sea12, Arca and Poetic. Winners also get an introduction to Peri's private talent network.

### Best use of deepagents, by LangChain (AIMING FOR THIS)
Teams build a deepagent for any use case they want. Switch 2 for winners.

### Arlequin AI, Track 2: Social Media Analysis: Combining Content & Connectivity Patterns (AIMING FOR THIS)
Our angle: make agents simulate social media trend behaviors online, reacting to the product.

Description: Build your own pipeline to explore and analyze networks, combining the semantic content of messages with the connectivity patterns between actors. One winner per track.

(Track 1, AI-Driven Forensics, is not our target: use AI (ML, DL and GenAI) techniques to uncover illegal and criminal patterns from forensic data.)
