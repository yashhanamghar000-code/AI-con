// AI-CON 25-Question Aptitude Assessment Definition
// Designed specifically for Class 10 students across 7 distinct aptitude dimensions.

const APTITUDE_QUESTIONS = [
  // ==========================================
  // 1. LOGICAL REASONING (4 Questions)
  // ==========================================
  {
    id: 1,
    category: "logical",
    categoryLabel: "Logical Reasoning",
    icon: "brain",
    question: "Find the next number in the following sequence: 3, 7, 15, 31, 63, ...",
    options: [
      { text: "95", scoreWeights: { science_pcm: 1, commerce_math: 0 } },
      { text: "127 (Rule: Previous × 2 + 1)", scoreWeights: { science_pcm: 4, commerce_math: 3, science_pcb: 2 }, isCorrect: true },
      { text: "125", scoreWeights: { science_pcm: 1, commerce_math: 1 } },
      { text: "129", scoreWeights: { science_pcm: 0, commerce_math: 0 } }
    ],
    hint: "Notice how each term relates to the previous one by doubling and adding 1."
  },
  {
    id: 2,
    category: "logical",
    categoryLabel: "Logical Reasoning",
    icon: "brain",
    question: "If all Engineers are Problem Solvers, and some Problem Solvers are Innovators, which statement is definitely true?",
    options: [
      { text: "All Innovators are Engineers", scoreWeights: { arts_humanities: 1 } },
      { text: "Some Engineers may be Innovators", scoreWeights: { science_pcm: 4, commerce_math: 3, arts_humanities: 3, analytical: 4 }, isCorrect: true },
      { text: "No Engineers are Innovators", scoreWeights: {} },
      { text: "All Problem Solvers are Engineers", scoreWeights: {} }
    ],
    hint: "Apply deductive syllogism to determine valid subset intersections."
  },
  {
    id: 3,
    category: "logical",
    categoryLabel: "Logical Reasoning",
    icon: "brain",
    question: "In a code language, if 'SMART' is coded as 'TNBSU' (each letter shifted forward by +1), how is 'SOLVE' coded?",
    options: [
      { text: "TPMWF", scoreWeights: { science_pcm: 4, commerce_math: 3, vocational: 2 }, isCorrect: true },
      { text: "TOMVF", scoreWeights: { science_pcm: 1 } },
      { text: "SPMWF", scoreWeights: {} },
      { text: "TNMWF", scoreWeights: {} }
    ],
    hint: "Shift each individual letter forward by one alphabetical position."
  },
  {
    id: 4,
    category: "logical",
    categoryLabel: "Logical Reasoning",
    icon: "brain",
    question: "Pointing to a photograph, Rohan said: 'She is the only daughter of my paternal grandfather's only son.' How is the person related to Rohan?",
    options: [
      { text: "Mother", scoreWeights: {} },
      { text: "Sister", scoreWeights: { science_pcm: 3, commerce_math: 3, arts_humanities: 3, analytical: 4 }, isCorrect: true },
      { text: "Aunt", scoreWeights: {} },
      { text: "Cousin", scoreWeights: {} }
    ],
    hint: "Paternal grandfather's only son is Rohan's father."
  },

  // ==========================================
  // 2. NUMERICAL APTITUDE (4 Questions)
  // ==========================================
  {
    id: 5,
    category: "numerical",
    categoryLabel: "Numerical Aptitude",
    icon: "calculator",
    question: "A store offers a 20% discount on a scientific calculator priced at ₹1,500. During checkout, an additional 10% loyalty discount is applied to the discounted price. What is the final price?",
    options: [
      { text: "₹1,050", scoreWeights: { commerce_math: 1 } },
      { text: "₹1,080", scoreWeights: { commerce_math: 4, science_pcm: 4, commerce_plain: 3 }, isCorrect: true },
      { text: "₹1,100", scoreWeights: { commerce_plain: 1 } },
      { text: "₹1,200", scoreWeights: {} }
    ],
    hint: "₹1,500 - 20% (₹300) = ₹1,200; then ₹1,200 - 10% (₹120) = ₹1,080."
  },
  {
    id: 6,
    category: "numerical",
    categoryLabel: "Numerical Aptitude",
    icon: "calculator",
    question: "A train travels from Mumbai to Pune (150 km) at an average speed of 60 km/h. On the return journey, it encounters traffic and travels at 40 km/h. What is the average speed for the entire round trip?",
    options: [
      { text: "50 km/h (arithmetic mean)", scoreWeights: {} },
      { text: "48 km/h (harmonic mean: 2×S1×S2 / (S1 + S2))", scoreWeights: { science_pcm: 4, commerce_math: 4 }, isCorrect: true },
      { text: "45 km/h", scoreWeights: { science_pcm: 1 } },
      { text: "52 km/h", scoreWeights: {} }
    ],
    hint: "Average speed is total distance (300 km) divided by total time (2.5h + 3.75h = 6.25h)."
  },
  {
    id: 7,
    category: "numerical",
    categoryLabel: "Numerical Aptitude",
    icon: "calculator",
    question: "If a sum of ₹10,000 earns ₹1,600 simple interest over 2 years, what is the annual rate of interest?",
    options: [
      { text: "6%", scoreWeights: {} },
      { text: "8%", scoreWeights: { commerce_math: 4, commerce_plain: 4, science_pcm: 3 }, isCorrect: true },
      { text: "10%", scoreWeights: {} },
      { text: "16%", scoreWeights: {} }
    ],
    hint: "Interest per year = ₹800. ₹800 / ₹10,000 = 8%."
  },
  {
    id: 8,
    category: "numerical",
    categoryLabel: "Numerical Aptitude",
    icon: "calculator",
    question: "In an examination, a student scores 4 marks for each correct answer and loses 1 mark for each wrong answer. If Priya answered all 60 questions and scored 190 marks, how many questions did she answer correctly?",
    options: [
      { text: "45", scoreWeights: {} },
      { text: "50 (4×50 - 1×10 = 190)", scoreWeights: { science_pcm: 4, commerce_math: 4 }, isCorrect: true },
      { text: "52", scoreWeights: {} },
      { text: "48", scoreWeights: {} }
    ],
    hint: "Let correct = C; 4C - (60 - C) = 190 => 5C = 250."
  },

  // ==========================================
  // 3. SCIENTIFIC THINKING (4 Questions)
  // ==========================================
  {
    id: 9,
    category: "scientific",
    categoryLabel: "Scientific Thinking",
    icon: "flask",
    question: "In a laboratory experiment testing how fertilizer affects plant growth, why is it essential to keep sunlight, water, and soil type identical across all pots?",
    options: [
      { text: "To make the experiment take less time", scoreWeights: {} },
      { text: "To ensure that differences in growth can only be attributed to the fertilizer (controlled variables)", scoreWeights: { science_pcb: 4, science_pcm: 4 }, isCorrect: true },
      { text: "Because plants cannot survive in different soil", scoreWeights: {} },
      { text: "To maximize the total number of plants produced", scoreWeights: {} }
    ],
    hint: "Scientific method requires controlling all extraneous variables."
  },
  {
    id: 10,
    category: "scientific",
    categoryLabel: "Scientific Thinking",
    icon: "flask",
    question: "When riding a bicycle uphill, switching to a smaller front gear and larger rear gear makes pedaling easier. What physical principle explains this trade-off?",
    options: [
      { text: "It reduces friction between tires and the road", scoreWeights: {} },
      { text: "Mechanical advantage: Trading force for distance (less pedal force required, but more revolutions needed)", scoreWeights: { science_pcm: 4, vocational: 4 }, isCorrect: true },
      { text: "It reduces the bicycle's total gravitational mass", scoreWeights: {} },
      { text: "It creates electrostatic propulsion", scoreWeights: {} }
    ],
    hint: "Work = Force × Distance. Mechanical advantage reduces the input force required."
  },
  {
    id: 11,
    category: "scientific",
    categoryLabel: "Scientific Thinking",
    icon: "flask",
    question: "Why do living organisms maintain a relatively constant internal body temperature and pH level despite changing external surroundings?",
    options: [
      { text: "Homeostasis: Essential for cellular enzymes to function effectively without denaturing", scoreWeights: { science_pcb: 4, science_pcm: 2 }, isCorrect: true },
      { text: "To prevent skin from changing color", scoreWeights: {} },
      { text: "Because internal organs have no contact with air", scoreWeights: {} },
      { text: "To increase total blood volume", scoreWeights: {} }
    ],
    hint: "Biological enzymes have strict optimal temperature and pH ranges."
  },
  {
    id: 12,
    category: "scientific",
    categoryLabel: "Scientific Thinking",
    icon: "flask",
    question: "When vinegar (acetic acid) is poured over baking soda (sodium bicarbonate), vigorous bubbling occurs. What gas is being released?",
    options: [
      { text: "Oxygen", scoreWeights: {} },
      { text: "Carbon Dioxide (CO₂)", scoreWeights: { science_pcb: 4, science_pcm: 4 }, isCorrect: true },
      { text: "Hydrogen", scoreWeights: {} },
      { text: "Nitrogen Dioxide", scoreWeights: {} }
    ],
    hint: "Carbonate + Acid produces salt, water, and carbon dioxide."
  },

  // ==========================================
  // 4. BUSINESS & FINANCIAL APTITUDE (4 Questions)
  // ==========================================
  {
    id: 13,
    category: "business",
    categoryLabel: "Business & Finance",
    icon: "trending-up",
    question: "A young entrepreneur produces handmade eco-friendly bags. Raw materials cost ₹80 per bag, and fixed shop rent is ₹6,000 per month. If bags are sold for ₹200 each, how many bags must be sold each month to break even?",
    options: [
      { text: "30 bags", scoreWeights: {} },
      { text: "50 bags (₹6,000 / (₹200 - ₹80) = 50)", scoreWeights: { commerce_plain: 4, commerce_math: 4 }, isCorrect: true },
      { text: "75 bags", scoreWeights: { commerce_plain: 1 } },
      { text: "100 bags", scoreWeights: {} }
    ],
    hint: "Break-even units = Fixed Costs / Contribution Margin per unit."
  },
  {
    id: 14,
    category: "business",
    categoryLabel: "Business & Finance",
    icon: "trending-up",
    question: "During festive season, why do flight and hotel ticket prices usually rise significantly?",
    options: [
      { text: "Government mandates higher tax rates during festivals", scoreWeights: {} },
      { text: "High consumer demand with limited seat/room supply drives prices upward (Demand-Supply dynamics)", scoreWeights: { commerce_plain: 4, commerce_math: 4, arts_humanities: 2 }, isCorrect: true },
      { text: "Airlines must pay higher fuel rates during holidays", scoreWeights: {} },
      { text: "Travel distance increases due to heavy air traffic", scoreWeights: {} }
    ],
    hint: "Market equilibrium shifts when demand surges against fixed capacity."
  },
  {
    id: 15,
    category: "business",
    categoryLabel: "Business & Finance",
    icon: "trending-up",
    question: "An investor can deposit ₹50,000 in a government guaranteed bond earning 7% annually, or invest in a new tech startup with a chance of 25% return but a risk of losing the capital. What financial concept does this represent?",
    options: [
      { text: "Inflation adjustment", scoreWeights: {} },
      { text: "The Risk-Return Trade-off", scoreWeights: { commerce_math: 4, commerce_plain: 4 }, isCorrect: true },
      { text: "Currency devaluation", scoreWeights: {} },
      { text: "Compound interest rule", scoreWeights: {} }
    ],
    hint: "Higher potential returns typically require taking on greater financial risk."
  },
  {
    id: 16,
    category: "business",
    categoryLabel: "Business & Finance",
    icon: "trending-up",
    question: "Which of the following is considered an asset rather than a liability for a business?",
    options: [
      { text: "A 5-year bank loan outstanding", scoreWeights: {} },
      { text: "Inventory of products ready for sale", scoreWeights: { commerce_plain: 4, commerce_math: 4 }, isCorrect: true },
      { text: "Unpaid electricity bills for the factory", scoreWeights: {} },
      { text: "Salaries owed to employees for the past month", scoreWeights: {} }
    ],
    hint: "An asset is an economic resource owned that will generate future benefit."
  },

  // ==========================================
  // 5. CREATIVE THINKING (3 Questions)
  // ==========================================
  {
    id: 17,
    category: "creative",
    categoryLabel: "Creative Thinking",
    icon: "palette",
    question: "When designing a mobile app for elderly citizens who may have weak eyesight, which design principle is most effective?",
    options: [
      { text: "Include bright glowing animations and intricate fine icons", scoreWeights: {} },
      { text: "High visual contrast, generous typography, uncluttered layouts, and large tactile tap targets", scoreWeights: { arts_humanities: 4, vocational: 3, science_pcm: 2 }, isCorrect: true },
      { text: "Fit as many features and buttons as possible on a single screen", scoreWeights: {} },
      { text: "Use light gray text on white background for minimalism", scoreWeights: {} }
    ],
    hint: "Human-centered design prioritizes accessibility and cognitive clarity."
  },
  {
    id: 18,
    category: "creative",
    categoryLabel: "Creative Thinking",
    icon: "palette",
    question: "In a creative advertising campaign for a water conservation initiative, which slogan uses the strongest conceptual metaphor?",
    options: [
      { text: "'Water is H2O with two hydrogen atoms.'", scoreWeights: { science_pcm: 1 } },
      { text: "'Every drop you save today is tomorrow's heartbeat.'", scoreWeights: { arts_humanities: 4, communication: 4 }, isCorrect: true },
      { text: "'Please turn off taps to reduce water meter readings.'", scoreWeights: { commerce_plain: 1 } },
      { text: "'Water flows downhill due to gravitational potential.'", scoreWeights: {} }
    ],
    hint: "Metaphor connects physical water to life and vitality."
  },
  {
    id: 19,
    category: "creative",
    categoryLabel: "Creative Thinking",
    icon: "palette",
    question: "You have 500 discarded plastic bottles from a school sports event. What is the most innovative sustainable design idea?",
    options: [
      { text: "Throw them all in standard trash bins", scoreWeights: {} },
      { text: "Upcycle them into a drip-irrigation vertical garden along the school boundary wall", scoreWeights: { arts_humanities: 4, vocational: 4, science_pcb: 3 }, isCorrect: true },
      { text: "Burn them in an open field", scoreWeights: {} },
      { text: "Store them in a closet indefinitely", scoreWeights: {} }
    ],
    hint: "Circular design transforms waste into functional community architecture."
  },

  // ==========================================
  // 6. COMMUNICATION & LANGUAGE (3 Questions)
  // ==========================================
  {
    id: 20,
    category: "communication",
    categoryLabel: "Communication & Language",
    icon: "message-square",
    question: "Complete the verbal analogy: 'STETHOSCOPE is to PHYSICIAN' as '______ is to ASTRONOMER'.",
    options: [
      { text: "Microscope", scoreWeights: { science_pcb: 1 } },
      { text: "Telescope", scoreWeights: { arts_humanities: 3, communication: 4, science_pcm: 3 }, isCorrect: true },
      { text: "Barometer", scoreWeights: {} },
      { text: "Periscope", scoreWeights: {} }
    ],
    hint: "A physician uses a stethoscope to examine patients; an astronomer uses a telescope to study celestial bodies."
  },
  {
    id: 21,
    category: "communication",
    categoryLabel: "Communication & Language",
    icon: "message-square",
    question: "Read the sentence: 'Despite facing formidable adversity and logistical shortages, the rescue expedition persevered relentlessly.' What does 'formidable' mean in this context?",
    options: [
      { text: "Minor and easily overlooked", scoreWeights: {} },
      { text: "Inspiring great respect or fear through being impressively powerful and challenging", scoreWeights: { arts_humanities: 4, communication: 4 }, isCorrect: true },
      { text: "Exciting and cheerful", scoreWeights: {} },
      { text: "Cost-effective", scoreWeights: {} }
    ],
    hint: "Formidable obstacles require immense effort and determination to overcome."
  },
  {
    id: 22,
    category: "communication",
    categoryLabel: "Communication & Language",
    icon: "message-square",
    question: "You need to convince your school principal to introduce a coding club. What is the most persuasive and professional approach?",
    options: [
      { text: "Complain publicly that the school is behind other schools in the city", scoreWeights: {} },
      { text: "Present a structured 1-page proposal outlining student benefits, proposed schedule, teacher mentor, and zero equipment cost", scoreWeights: { communication: 4, arts_humanities: 3, commerce_plain: 3 }, isCorrect: true },
      { text: "Ask parents to call the principal repeatedly", scoreWeights: {} },
      { text: "Post a petition on social media before talking to the principal", scoreWeights: {} }
    ],
    hint: "Professional persuasion combines structured facts, clear benefits, and operational feasibility."
  },

  // ==========================================
  // 7. ANALYTICAL PROBLEM-SOLVING (3 Questions)
  // ==========================================
  {
    id: 23,
    category: "analytical",
    categoryLabel: "Analytical Problem-Solving",
    icon: "cpu",
    question: "A solar-powered streetlamp suddenly stops lighting up at night. What is the most logical first step in troubleshooting the problem?",
    options: [
      { text: "Replace the entire solar pole with a brand new unit", scoreWeights: {} },
      { text: "Systematically test components in sequence: Check if solar panel is clean/charging, inspect battery voltage, then test LED bulb connection", scoreWeights: { science_pcm: 4, vocational: 4, analytical: 4 }, isCorrect: true },
      { text: "Wait for a week to see if weather improves", scoreWeights: {} },
      { text: "Paint the pole to prevent rust", scoreWeights: {} }
    ],
    hint: "Root cause analysis isolates variables from power source to load."
  },
  {
    id: 24,
    category: "analytical",
    categoryLabel: "Analytical Problem-Solving",
    icon: "cpu",
    question: "You have 3 days before school science exhibition. Task A requires 6 hours and must be done first. Task B and Task C each require 4 hours and can be done simultaneously. Task D (final testing) takes 2 hours and requires all tasks to be complete. What is the critical path duration?",
    options: [
      { text: "16 hours", scoreWeights: {} },
      { text: "12 hours (Task A [6h] + max(Task B, Task C) [4h] + Task D [2h] = 12h)", scoreWeights: { science_pcm: 4, commerce_math: 4, analytical: 4 }, isCorrect: true },
      { text: "10 hours", scoreWeights: {} },
      { text: "14 hours", scoreWeights: {} }
    ],
    hint: "Critical path represents the longest sequence of dependent events."
  },
  {
    id: 25,
    category: "analytical",
    categoryLabel: "Analytical Problem-Solving",
    icon: "cpu",
    question: "A team needs to deliver a project on time. The client asks for 5 extra features without extending the deadline or increasing the budget. As project lead, what is the best trade-off strategy?",
    options: [
      { text: "Agree immediately and force team to work without sleep", scoreWeights: {} },
      { text: "Prioritize features by business value, deliver core features on time, and schedule secondary features for Phase 2", scoreWeights: { commerce_plain: 4, commerce_math: 4, analytical: 4 }, isCorrect: true },
      { text: "Cancel the entire contract in frustration", scoreWeights: {} },
      { text: "Deliver half-finished buggy code to meet the date", scoreWeights: {} }
    ],
    hint: "Effective project management balances scope, time, and quality sustainably."
  }
];

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { APTITUDE_QUESTIONS };
}
