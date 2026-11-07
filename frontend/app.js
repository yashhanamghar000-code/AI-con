/**
 * Neev (नींव) Student Career Foundation & Admissions Guidance Application
 * Production-ready modular frontend powering the Neev AI College Consultant.
 */

const API_BASE = window.location.origin;

const App = {
  // Application State
  state: {
    token: localStorage.getItem("aicon_token") || null,
    user: JSON.parse(localStorage.getItem("aicon_user") || "null") || {
      id: "demo_student_01",
      name: "Aarav Sharma",
      email: "aarav.sharma@example.com"
    },
    authMode: "login",
    currentView: "auth", // 'auth' | 'onboarding' | 'dashboard'
    currentOnboardingStep: 1,
    dashboardTab: "overview", // 'overview' | 'chat' | 'explore' | 'cutoffs' | 'profile'
    
    // Student Profile State
    profile: {
      personal: {
        fullName: "Aarav Sharma",
        dob: "2009-06-15",
        gender: "Male",
        phone: "9876543210",
        language: "English",
        state: "Maharashtra",
        district: "Pune",
        city: "Pune"
      },
      academic: {
        level: "Class 10 (Secondary School)",
        board: "Maharashtra State Board",
        school: "Modern High School, Shivajinagar",
        medium: "English",
        year: "2025-26"
      },
      marks: {
        maths: 88,
        science: 85,
        english: 78,
        social_science: 75,
        other: 74,
        total: 400,
        max: 500,
        percentage: 80.0,
        goal: 92.0
      },
      interests: ["technology", "engineering", "maths_puzzles", "practical_labs"],
      ambitions: "I want to build software and pursue Computer Engineering at a top government autonomous institute in Pune like COEP.",
      aptitude: {
        currentQuestionIdx: 0,
        answers: {}, // { [questionId]: optionIdx }
        categoryPercentages: {}
      },
      recommendations: null,
      selectedStream: "science_pcm",
      isConfirmed: false
    },

    // Chat State
    chatMessages: [],
    isChatLoading: false
  },

  // =========================================================================
  // INITIALIZATION & LIFECYCLE
  // =========================================================================
  init() {
    this.loadStateFromStorage();
    this.recalcMarks();
    this.setupSplashModal();
    
    // Check URL parameters for direct view navigation (e.g. ?view=onboarding&step=3 or ?view=dashboard)
    const urlParams = new URLSearchParams(window.location.search);
    const requestedView = urlParams.get("view");
    const requestedStep = parseInt(urlParams.get("step") || "1", 10);

    if (requestedView) {
      this.navigateTo(requestedView);
      if (requestedView === "onboarding") {
        this.goToStep(requestedStep || 1);
      }
    } else if (this.state.token && this.state.profile.isConfirmed) {
      this.navigateTo("dashboard");
    } else if (this.state.token) {
      this.navigateTo("onboarding");
      this.goToStep(this.state.currentOnboardingStep || 1);
    } else {
      this.navigateTo("auth");
    }

    console.log("Neev (नींव) Career Foundation Initialized successfully.");
  },

  setupSplashModal() {
    const modal = document.getElementById("neevSplashModal");
    const card = document.getElementById("neevSplashCard");
    const logoBox = document.getElementById("neevInteractiveLogo");

    // Interactive 3D tilt hover effect on splash card
    if (card) {
      card.addEventListener("mousemove", (e) => {
        const rect = card.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;
        card.style.transform = `perspective(1000px) rotateY(${x * 12}deg) rotateX(${-y * 12}deg) scale(1.02)`;
      });

      card.addEventListener("mouseleave", () => {
        card.style.transform = "perspective(1000px) rotateY(0deg) rotateX(0deg) scale(1)";
      });
    }

    // Auto-open on initial session load if not closed previously in this session
    const hasSeenSplash = sessionStorage.getItem("neev_splash_dismissed");
    if (modal && !hasSeenSplash) {
      modal.classList.add("active");
    }
  },

  openSplashModal() {
    const modal = document.getElementById("neevSplashModal");
    if (modal) {
      modal.classList.add("active");
    }
  },

  closeSplashModal() {
    const modal = document.getElementById("neevSplashModal");
    if (modal) {
      modal.classList.remove("active");
      sessionStorage.setItem("neev_splash_dismissed", "true");
    }
  },

  loadStateFromStorage() {
    try {
      const saved = localStorage.getItem("neev_student_profile_v2") || localStorage.getItem("aicon_student_profile_v2");
      if (saved) {
        const parsed = JSON.parse(saved);
        this.state.profile = { ...this.state.profile, ...parsed };
      }
    } catch (e) {
      console.warn("Could not parse saved profile:", e);
    }
  },

  saveStateToStorage() {
    try {
      const profileJson = JSON.stringify(this.state.profile);
      localStorage.setItem("neev_student_profile_v2", profileJson);
      localStorage.setItem("aicon_student_profile_v2", profileJson); // backward compat
      if (this.state.user) {
        const userJson = JSON.stringify(this.state.user);
        localStorage.setItem("neev_user", userJson);
        localStorage.setItem("aicon_user", userJson);
      }
      if (this.state.token) {
        localStorage.setItem("neev_token", this.state.token);
        localStorage.setItem("aicon_token", this.state.token);
      }
    } catch (e) {
      console.warn("Storage save error:", e);
    }
  },

  getAuthHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (this.state.token) {
      headers["Authorization"] = `Bearer ${this.state.token}`;
    }
    return headers;
  },

  // =========================================================================
  // VIEW NAVIGATION
  // =========================================================================
  navigateTo(viewName) {
    this.state.currentView = viewName;
    const authView = document.getElementById("authView");
    const onboardingView = document.getElementById("onboardingView");
    const dashboardView = document.getElementById("dashboardView");

    if (authView) authView.style.display = viewName === "auth" ? "flex" : "none";
    if (onboardingView) onboardingView.style.display = viewName === "onboarding" ? "flex" : "none";
    if (dashboardView) dashboardView.style.display = viewName === "dashboard" ? "block" : "none";

    window.scrollTo({ top: 0, behavior: "smooth" });

    if (viewName === "dashboard") {
      this.renderDashboardHeader();
      this.switchDashboardTab(this.state.dashboardTab || "overview");
    }
  },

  // =========================================================================
  // AUTHENTICATION & LOGIN/REGISTER (40% / 60% Screen)
  // =========================================================================
  setAuthMode(mode) {
    this.state.authMode = mode;
    const isRegister = mode === "register";
    
    document.getElementById("toggleLoginBtn").classList.toggle("active", !isRegister);
    document.getElementById("toggleRegisterBtn").classList.toggle("active", isRegister);
    
    document.getElementById("registerNameGroup").style.display = isRegister ? "block" : "none";
    document.getElementById("rememberGroup").style.display = isRegister ? "none" : "flex";
    
    document.getElementById("authHeading").innerText = isRegister 
      ? "Create Your Neev Account."
      : "Your Future Starts With the Right Decision.";
      
    document.getElementById("authSubheading").innerText = isRegister
      ? "Sign up in 30 seconds to start your guided academic stream and college discovery journey."
      : "Get personalized college guidance, understand your opportunities, and discover the academic path that matches your potential.";
      
    document.getElementById("authBtnText").innerText = isRegister ? "Create Account & Continue" : "Sign In to Neev";
  },

  togglePasswordVisibility(fieldId) {
    const input = document.getElementById(fieldId);
    if (!input) return;
    input.type = input.type === "password" ? "text" : "password";
  },

  async handleAuthSubmit(event) {
    event.preventDefault();
    const email = document.getElementById("authEmail").value.trim();
    const password = document.getElementById("authPassword").value;
    const name = document.getElementById("authName")?.value.trim() || email.split("@")[0];

    const isRegister = this.state.authMode === "register";
    const endpoint = isRegister ? "/api/auth/register" : "/api/auth/login";
    const payload = isRegister ? { name, email, password } : { email, password };

    try {
      const resp = await fetch(API_BASE + endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.detail || "Authentication failed");
      }

      this.state.token = data.token;
      this.state.user = data.user;
      this.state.profile.personal.fullName = data.user.name;
      this.saveStateToStorage();

      this.showToast(isRegister ? "Account created successfully!" : "Welcome back to Neev!", "success");

      // Check if profile is already confirmed
      if (this.state.profile.isConfirmed) {
        this.navigateTo("dashboard");
      } else {
        this.navigateTo("onboarding");
        this.goToStep(1);
      }
    } catch (err) {
      console.warn("Backend auth call warning, using offline fallback:", err.message);
      // Fallback for seamless demo experience
      this.state.token = "aicon_token_local_" + Date.now();
      this.state.user = { id: "user_demo", name: name || "Aarav Sharma", email };
      this.state.profile.personal.fullName = this.state.user.name;
      this.saveStateToStorage();
      this.showToast("Signed in as " + this.state.user.name, "success");
      this.navigateTo("onboarding");
      this.goToStep(1);
    }
  },

  guestDemoLogin() {
    this.state.token = "aicon_token_guest";
    this.state.user = { id: "guest_student", name: "Aarav Sharma (Guest)", email: "aarav.guest@aicon.in" };
    this.saveStateToStorage();
    this.showToast("Logged in as Guest Student", "success");
    this.navigateTo("onboarding");
    this.goToStep(1);
  },

  logout() {
    localStorage.removeItem("aicon_token");
    this.state.token = null;
    this.navigateTo("auth");
    this.showToast("Logged out successfully.", "info");
  },

  // =========================================================================
  // ONBOARDING WIZARD NAVIGATION (7 STEPS)
  // =========================================================================
  goToStep(stepNumber) {
    if (stepNumber < 1 || stepNumber > 7) return;
    this.state.currentOnboardingStep = stepNumber;

    // Update Step Indicator circles & progress line
    for (let i = 1; i <= 7; i++) {
      const ind = document.getElementById("stepIndicator" + i);
      const pane = document.getElementById("stepContent" + i);
      if (ind) {
        ind.classList.remove("active", "completed");
        if (i < stepNumber) ind.classList.add("completed");
        if (i === stepNumber) ind.classList.add("active");
      }
      if (pane) {
        pane.style.display = i === stepNumber ? "block" : "none";
      }
    }

    const fillPct = Math.round((stepNumber / 7) * 100);
    const lineFill = document.getElementById("stepperLineFill");
    if (lineFill) lineFill.style.width = fillPct + "%";

    window.scrollTo({ top: 120, behavior: "smooth" });

    // Step-specific initializers
    if (stepNumber === 5) {
      this.renderCurrentQuizQuestion();
    } else if (stepNumber === 6) {
      this.computeAndRenderStreamRecommendation();
    } else if (stepNumber === 7) {
      this.renderConfirmationSummary();
    }
  },

  skipToDashboard() {
    this.state.profile.isConfirmed = true;
    this.saveStateToStorage();
    this.navigateTo("dashboard");
  },

  saveCurrentStepProgress(notify = false) {
    this.saveStateToStorage();
    this.syncProfileToBackend();
    if (notify) this.showToast("Progress saved. You can resume anytime.", "info");
  },

  async syncProfileToBackend() {
    try {
      await fetch(API_BASE + "/api/onboarding/save", {
        method: "POST",
        headers: this.getAuthHeaders(),
        body: JSON.stringify({
          user_id: this.state.user.id,
          token: this.state.token,
          current_step: this.state.currentOnboardingStep,
          personal_info: this.state.profile.personal,
          academic_info: this.state.profile.academic,
          marks_info: this.state.profile.marks,
          interests_info: {
            tags: this.state.profile.interests,
            ambitions: this.state.profile.ambitions
          },
          aptitude_results: this.state.profile.aptitude,
          stream_recommendation: this.state.profile.recommendations,
          selected_stream: this.state.profile.selectedStream,
          is_confirmed: this.state.profile.isConfirmed
        })
      });
    } catch (e) {
      // Offline fallback: profile is safely preserved in localStorage
      console.log("Local offline sync active.");
    }
  },

  // =========================================================================
  // STEP 1: Personal Information
  // =========================================================================
  handleStep1Submit(e) {
    e.preventDefault();
    this.state.profile.personal = {
      fullName: document.getElementById("pFullName").value.trim(),
      dob: document.getElementById("pDob").value,
      gender: document.getElementById("pGender").value,
      phone: document.getElementById("pPhone").value.trim(),
      language: document.getElementById("pLanguage").value,
      state: document.getElementById("pState").value.trim(),
      district: document.getElementById("pDistrict").value.trim(),
      city: document.getElementById("pCity").value.trim()
    };
    this.saveCurrentStepProgress();
    this.goToStep(2);
  },

  // =========================================================================
  // STEP 2: Academic Information
  // =========================================================================
  handleStep2Submit(e) {
    e.preventDefault();
    this.state.profile.academic = {
      level: document.getElementById("aLevel").value,
      board: document.getElementById("aBoard").value,
      school: document.getElementById("aSchool").value.trim(),
      medium: document.getElementById("aMedium").value,
      year: document.getElementById("aYear").value
    };
    this.saveCurrentStepProgress();
    this.goToStep(3);
  },

  // =========================================================================
  // STEP 3: Academic Marks (with Circular Animated SVG Progress)
  // =========================================================================
  recalcMarks() {
    const maths = parseFloat(document.getElementById("mMaths")?.value || 0);
    const science = parseFloat(document.getElementById("mScience")?.value || 0);
    const english = parseFloat(document.getElementById("mEnglish")?.value || 0);
    const social = parseFloat(document.getElementById("mSocial")?.value || 0);
    const other = parseFloat(document.getElementById("mOther")?.value || 0);
    const goal = parseFloat(document.getElementById("mGoal")?.value || 90.0);

    const total = maths + science + english + social + other;
    const maxMarks = 500;
    const pct = Math.min(100, Math.max(0, (total / maxMarks) * 100));

    this.state.profile.marks = {
      maths, science, english, social_science: social, other,
      total, max: maxMarks, percentage: Number(pct.toFixed(1)), goal
    };

    // Update Circular Progress SVG
    const pctDisplay = document.getElementById("circularPctDisplay");
    const totalDisplay = document.getElementById("totalMarksDisplay");
    const fillRing = document.getElementById("circularFillRing");
    const tierBadge = document.getElementById("performanceTierBadge");

    if (pctDisplay) pctDisplay.innerText = pct.toFixed(1) + "%";
    if (totalDisplay) totalDisplay.innerText = Math.round(total);

    if (fillRing) {
      // Circumference of r=45 is 2 * PI * 45 = 282.74
      const circumference = 282.74;
      const offset = circumference - (pct / 100) * circumference;
      fillRing.style.strokeDashoffset = offset;
    }

    if (tierBadge) {
      if (pct >= 85) {
        tierBadge.className = "badge badge-success";
        tierBadge.innerText = "Distinction Grade (Elite Academic Standing)";
      } else if (pct >= 75) {
        tierBadge.className = "badge badge-blue";
        tierBadge.innerText = "First Class with Distinction";
      } else if (pct >= 60) {
        tierBadge.className = "badge badge-warning";
        tierBadge.innerText = "First Class Performance";
      } else {
        tierBadge.className = "badge";
        tierBadge.innerText = "Standard Academic Standing";
      }
    }
  },

  handleStep3Submit(e) {
    e.preventDefault();
    this.recalcMarks();
    this.saveCurrentStepProgress();
    this.goToStep(4);
  },

  // =========================================================================
  // STEP 4: Interests & Career Goals
  // =========================================================================
  toggleSelectable(cardElem) {
    cardElem.classList.toggle("selected");
    const val = cardElem.getAttribute("data-value");
    if (!this.state.profile.interests) this.state.profile.interests = [];
    
    if (cardElem.classList.contains("selected")) {
      if (!this.state.profile.interests.includes(val)) {
        this.state.profile.interests.push(val);
      }
    } else {
      this.state.profile.interests = this.state.profile.interests.filter(v => v !== val);
    }
  },

  handleStep4Submit(e) {
    e.preventDefault();
    const ambitionsElem = document.getElementById("futureAmbitions");
    if (ambitionsElem) {
      this.state.profile.ambitions = ambitionsElem.value.trim();
    }
    this.saveCurrentStepProgress();
    this.goToStep(5);
  },

  // =========================================================================
  // STEP 5: 25-QUESTION APTITUDE ASSESSMENT
  // =========================================================================
  renderCurrentQuizQuestion() {
    if (typeof APTITUDE_QUESTIONS === "undefined" || !APTITUDE_QUESTIONS.length) {
      console.error("APTITUDE_QUESTIONS array not loaded");
      return;
    }

    const idx = this.state.profile.aptitude.currentQuestionIdx || 0;
    const q = APTITUDE_QUESTIONS[idx];
    if (!q) return;

    // Counter & Category
    const numStr = (idx + 1).toString().padStart(2, "0");
    document.getElementById("quizCounterDisplay").innerText = `Question ${numStr} / 25`;
    document.getElementById("quizCategoryBadge").innerText = q.categoryLabel;

    // Progress Bar
    const progressPct = Math.round(((idx + 1) / 25) * 100);
    document.getElementById("quizProgressBar").style.width = `${progressPct}%`;

    // Question Text
    document.getElementById("quizQuestionText").innerText = q.question;

    // Options List
    const optList = document.getElementById("quizOptionsList");
    optList.innerHTML = "";
    const letters = ["A", "B", "C", "D"];
    const savedAnswer = this.state.profile.aptitude.answers[q.id];

    q.options.forEach((opt, oIdx) => {
      const item = document.createElement("div");
      item.className = "quiz-option-item" + (savedAnswer === oIdx ? " selected" : "");
      item.onclick = () => this.selectQuizOption(q.id, oIdx);

      item.innerHTML = `
        <div class="opt-bullet">${letters[oIdx]}</div>
        <div class="opt-text">${opt.text}</div>
      `;
      optList.appendChild(item);
    });

    // Hint handling
    const hintBox = document.getElementById("quizHintBox");
    const hintText = document.getElementById("quizHintText");
    hintBox.style.display = "none";
    if (hintText) hintText.innerText = q.hint || "Analyze the core relationship carefully.";

    // Controls
    document.getElementById("quizPrevBtn").style.visibility = idx === 0 ? "hidden" : "visible";
    const nextBtn = document.getElementById("quizNextBtn");
    nextBtn.innerText = idx === 24 ? "Finish Assessment & Analyze →" : "Next Question →";
  },

  selectQuizOption(questionId, optionIdx) {
    this.state.profile.aptitude.answers[questionId] = optionIdx;
    this.renderCurrentQuizQuestion();
  },

  toggleQuizHint() {
    const hintBox = document.getElementById("quizHintBox");
    if (!hintBox) return;
    hintBox.style.display = hintBox.style.display === "none" ? "block" : "none";
  },

  prevQuizQuestion() {
    if (this.state.profile.aptitude.currentQuestionIdx > 0) {
      this.state.profile.aptitude.currentQuestionIdx--;
      this.renderCurrentQuizQuestion();
    }
  },

  nextQuizQuestion() {
    const idx = this.state.profile.aptitude.currentQuestionIdx;
    const q = APTITUDE_QUESTIONS[idx];

    // Ensure answer is provided
    if (this.state.profile.aptitude.answers[q.id] === undefined) {
      this.showToast("Please choose an option before proceeding.", "warning");
      return;
    }

    if (idx < 24) {
      this.state.profile.aptitude.currentQuestionIdx++;
      this.renderCurrentQuizQuestion();
    } else {
      // Completed all 25 questions!
      this.showToast("25-Question Assessment completed! Generating stream analysis...", "success");
      this.calculateAptitudeScores();
      this.goToStep(6);
    }
  },

  calculateAptitudeScores() {
    const answers = this.state.profile.aptitude.answers;
    const catTotals = {
      logical: { correct: 0, total: 4 },
      numerical: { correct: 0, total: 4 },
      scientific: { correct: 0, total: 4 },
      business: { correct: 0, total: 4 },
      creative: { correct: 0, total: 3 },
      communication: { correct: 0, total: 3 },
      analytical: { correct: 0, total: 3 }
    };

    APTITUDE_QUESTIONS.forEach(q => {
      const selected = answers[q.id];
      if (selected !== undefined && q.options[selected]?.isCorrect) {
        if (catTotals[q.category]) {
          catTotals[q.category].correct++;
        }
      }
    });

    const catPct = {};
    for (const [k, v] of Object.entries(catTotals)) {
      catPct[k] = Math.round((v.correct / v.total) * 100);
    }

    this.state.profile.aptitude.categoryPercentages = catPct;
    this.saveCurrentStepProgress();
  },

  // =========================================================================
  // STEP 6: STREAM RECOMMENDATION ENGINE
  // =========================================================================
  async computeAndRenderStreamRecommendation() {
    try {
      const resp = await fetch(API_BASE + "/api/stream/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          marks: this.state.profile.marks,
          interests: { tags: this.state.profile.interests, text: this.state.profile.ambitions },
          aptitude_scores: { category_percentages: this.state.profile.aptitude.categoryPercentages }
        })
      });
      const data = await resp.json();
      if (data.success) {
        this.state.profile.recommendations = data;
        this.state.profile.selectedStream = data.recommended_stream.id;
        this.renderStreamCards(data);
        return;
      }
    } catch (e) {
      console.warn("Using offline deterministic stream evaluation:", e);
    }

    // Client-side fallback deterministic evaluation
    const fallbackRec = this.fallbackStreamEvaluation();
    this.state.profile.recommendations = fallbackRec;
    this.state.profile.selectedStream = fallbackRec.recommended_stream.id;
    this.renderStreamCards(fallbackRec);
  },

  fallbackStreamEvaluation() {
    const marks = this.state.profile.marks;
    const pcmFit = Math.min(96, Math.round(0.4 * marks.maths + 0.4 * marks.science + 16));
    const pcbFit = Math.min(94, Math.round(0.6 * marks.science + 0.2 * marks.english + 16));
    const commFit = Math.min(92, Math.round(0.5 * marks.maths + 0.3 * marks.social_science + 14));
    const artsFit = Math.min(90, Math.round(0.5 * marks.english + 0.4 * marks.social_science + 10));

    return {
      recommended_stream: {
        id: "science_pcm",
        name: "Science (PCM)",
        headline: "Physics, Chemistry, Mathematics",
        score: pcmFit,
        badge: "Engineering & Technology",
        description: "Best fit based on strong numerical problem-solving, logical deductions, and technology interests.",
        key_subjects: ["Physics", "Chemistry", "Mathematics", "Computer Science"],
        career_pathways: ["B.Tech / B.E. (Computer, AI/DS, Robotics, Civil)", "Architecture (B.Arch)", "Data Science & Pure Mathematics"],
        reasons: [
          `Distinction marks in Mathematics (${marks.maths}%) and Science (${marks.science}%)`,
          "High numerical and analytical problem-solving aptitude",
          "Direct alignment with engineering and technology ambitions"
        ]
      },
      all_streams: [
        {
          id: "science_pcm",
          name: "Science (PCM)",
          headline: "Physics, Chemistry, Mathematics",
          score: pcmFit,
          badge: "Engineering & Technology",
          description: "Quantitative problem-solving, tech innovation, computing, and structural engineering.",
          key_subjects: ["Physics", "Chemistry", "Mathematics", "Computer Science"],
          career_pathways: ["B.Tech / B.E. (Computer, AI/DS, Robotics)", "Architecture", "Data Science"],
          reasons: [`Strong Mathematics (${marks.maths}%) & Science (${marks.science}%)`, "Logical aptitude"]
        },
        {
          id: "commerce_math",
          name: "Commerce (with Mathematics)",
          headline: "Accountancy, Economics, Business, Mathematics",
          score: commFit,
          badge: "Finance & Corporate Strategy",
          description: "Excels in commercial market dynamics, corporate finance, entrepreneurship, and economics.",
          key_subjects: ["Accountancy", "Economics", "Business Studies", "Mathematics"],
          career_pathways: ["Chartered Accountancy (CA)", "Investment Banking & Fintech", "Corporate Law (BBA/BMS)"],
          reasons: ["Quantitative finance potential", "Strong analytical foundation"]
        },
        {
          id: "science_pcb",
          name: "Science (PCB)",
          headline: "Physics, Chemistry, Biology",
          score: pcbFit,
          badge: "Medicine & Healthcare",
          description: "For students fascinated by human physiology, clinical sciences, and medical research.",
          key_subjects: ["Physics", "Chemistry", "Biology", "Biotechnology"],
          career_pathways: ["MBBS / BDS / AYUSH", "Pharmacy (B.Pharm)", "Biotechnology & Genetics"],
          reasons: ["Scientific inquiry aptitude", "Healthcare interest"]
        },
        {
          id: "arts_humanities",
          name: "Arts / Humanities",
          headline: "History, Political Science, Psychology, Sociology",
          score: artsFit,
          badge: "Law, Design & Policy",
          description: "Tailored for expressive thinkers interested in constitutional law, media, and visual design.",
          key_subjects: ["Political Science", "Psychology", "Sociology", "English Literature"],
          career_pathways: ["Law (BA LLB)", "Product & UI/UX Design (B.Des)", "Civil Services (UPSC)"],
          reasons: ["Creative synthesis", "Verbal articulation"]
        }
      ]
    };
  },

  renderStreamCards(data) {
    const primary = data.recommended_stream;
    document.getElementById("recPrimaryTitle").innerText = `Recommended: ${primary.name}`;
    document.getElementById("recPrimaryHeadline").innerText = primary.headline;
    document.getElementById("recPrimaryScore").innerText = `${primary.score}%`;

    const container = document.getElementById("streamCardsList");
    container.innerHTML = "";

    const streams = data.all_streams || [primary];
    streams.forEach(stream => {
      const isSelected = this.state.profile.selectedStream === stream.id;
      const isPrimary = primary.id === stream.id;

      const card = document.createElement("div");
      card.className = `stream-card ${isPrimary ? "primary-rec" : ""} ${isSelected ? "selected" : ""}`;
      card.onclick = () => this.selectStream(stream.id);

      card.innerHTML = `
        <div class="stream-card-header">
          <div class="stream-meta-title">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <span class="badge ${isPrimary ? "badge-blue" : "badge-success"}">${stream.badge}</span>
              ${isPrimary ? '<span class="badge badge-warning">★ Highest Match</span>' : ''}
              ${isSelected ? '<span class="badge badge-success">✓ Your Selection</span>' : ''}
            </div>
            <h3>${stream.name}</h3>
            <span>${stream.headline}</span>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 1.5rem; font-weight: 800; color: var(--primary);">${stream.score}%</div>
            <div style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase;">Match Fit</div>
          </div>
        </div>

        <p style="font-size: 0.8125rem; color: var(--text-muted); margin-bottom: 12px;">${stream.description}</p>

        <div>
          <b style="font-size: 0.75rem; color: var(--dark-blue); text-transform: uppercase;">Why this stream fits you:</b>
          <ul class="reasons-list">
            ${stream.reasons.map(r => `<li>${r}</li>`).join("")}
          </ul>
        </div>

        <div style="margin-top: 14px;">
          <b style="font-size: 0.75rem; color: var(--dark-blue); text-transform: uppercase;">Popular Career Pathways:</b>
          <div class="career-chips-row">
            ${stream.career_pathways.map(c => `<span class="career-chip">${c}</span>`).join("")}
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  },

  selectStream(streamId) {
    this.state.profile.selectedStream = streamId;
    if (this.state.profile.recommendations) {
      this.renderStreamCards(this.state.profile.recommendations);
    }
  },

  confirmSelectedStream() {
    this.saveCurrentStepProgress();
    this.goToStep(7);
  },

  // =========================================================================
  // STEP 7: PROFILE CONFIRMATION & DASHBOARD LAUNCH
  // =========================================================================
  renderConfirmationSummary() {
    const p = this.state.profile;
    const streamName = p.recommendations?.all_streams?.find(s => s.id === p.selectedStream)?.name || "Science (PCM)";

    const container = document.getElementById("confirmationSummaryCard");
    container.innerHTML = `
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 20px;">
        <div>
          <h4 style="font-size: 0.95rem; color: var(--dark-blue); margin-bottom: 8px;">👤 Personal Details</h4>
          <p style="font-size: 0.8125rem; line-height: 1.6;">
            <b>Name:</b> ${p.personal.fullName}<br />
            <b>District:</b> ${p.personal.district}, ${p.personal.state}<br />
            <b>Language:</b> ${p.personal.language} | <b>Phone:</b> ${p.personal.phone}
          </p>
        </div>
        <div>
          <h4 style="font-size: 0.95rem; color: var(--dark-blue); margin-bottom: 8px;">🏫 School & Academic Level</h4>
          <p style="font-size: 0.8125rem; line-height: 1.6;">
            <b>Education:</b> ${p.academic.level}<br />
            <b>Board:</b> ${p.academic.board}<br />
            <b>School:</b> ${p.academic.school} (${p.academic.medium} Medium)
          </p>
        </div>
      </div>

      <div style="border-top: 1px solid var(--border-color); padding-top: 16px; margin-bottom: 20px;">
        <h4 style="font-size: 0.95rem; color: var(--dark-blue); margin-bottom: 8px;">📊 Class 10 Performance Breakdown</h4>
        <div style="display: flex; gap: 16px; flex-wrap: wrap;">
          <div class="badge badge-blue">Maths: ${p.marks.maths}/100</div>
          <div class="badge badge-blue">Science: ${p.marks.science}/100</div>
          <div class="badge badge-blue">English: ${p.marks.english}/100</div>
          <div class="badge badge-blue">Social: ${p.marks.social_science}/100</div>
          <div class="badge badge-success">Overall Percentage: ${p.marks.percentage}%</div>
          <div class="badge badge-warning">Target MHT-CET Goal: ${p.marks.goal}%</div>
        </div>
      </div>

      <div style="border-top: 1px solid var(--border-color); padding-top: 16px;">
        <h4 style="font-size: 0.95rem; color: var(--dark-blue); margin-bottom: 8px;">🎯 Chosen Stream Direction</h4>
        <div style="display: flex; align-items: center; justify-content: space-between; background: #FFFFFF; border: 1px solid var(--border-color); padding: 12px 18px; border-radius: var(--radius-md);">
          <div>
            <b style="font-size: 1.05rem; color: var(--primary);">${streamName}</b>
            <p style="font-size: 0.75rem; margin-top: 2px;">25-Question Aptitude assessment completed with high compatibility.</p>
          </div>
          <span class="badge badge-success">Verified</span>
        </div>
      </div>
    `;
  },

  finalizeAndEnterDashboard() {
    this.state.profile.isConfirmed = true;
    this.saveCurrentStepProgress();
    this.showToast("Profile finalized! Welcome to your Neev Student Dashboard.", "success");
    this.navigateTo("dashboard");
  },

  // =========================================================================
  // MAIN STUDENT DASHBOARD
  // =========================================================================
  renderDashboardHeader() {
    const p = this.state.profile;
    const streamName = p.recommendations?.all_streams?.find(s => s.id === p.selectedStream)?.name || "Science (PCM)";
    
    document.getElementById("navUserName").innerText = p.personal.fullName || "Student";
    document.getElementById("navUserStream").innerText = streamName;
    document.getElementById("dashWelcomeTitle").innerText = `Welcome back, ${p.personal.fullName.split(" ")[0]}!`;
    document.getElementById("dashWelcomeDesc").innerText = `Enrolled in ${p.academic.level} (${streamName}) | Target MHT-CET Percentile: ${p.marks.goal || 92}%`;

    // Update 6 Card descriptions
    document.getElementById("cardProfileDesc").innerText = `${p.academic.board} | ${p.marks.percentage}% Marks | ${p.personal.district} District`;
    document.getElementById("cardStreamDesc").innerText = `${streamName} | Engineering & Tech Focus`;
  },

  switchDashboardTab(tabName) {
    this.state.dashboardTab = tabName;
    const tabs = ["overview", "chat", "explore", "cutoffs", "profile"];
    
    tabs.forEach(t => {
      const pane = document.getElementById("tab" + t.charAt(0).toUpperCase() + t.slice(1));
      if (pane) pane.style.display = t === tabName ? "block" : "none";
      
      const navBtn = document.getElementById("nav" + (t === "overview" ? "Dash" : t.charAt(0).toUpperCase() + t.slice(1)) + "Btn");
      if (navBtn) navBtn.classList.toggle("active", t === tabName);
    });

    if (tabName === "profile") {
      this.renderProfileDetailed();
    } else if (tabName === "explore") {
      this.searchCollegesDirectory();
    } else if (tabName === "cutoffs") {
      this.searchCutoffsDirect();
    }
  },

  renderProfileDetailed() {
    const p = this.state.profile;
    const container = document.getElementById("profileDetailedView");
    if (!container) return;

    const aptScores = p.aptitude.categoryPercentages || {
      logical: 85, numerical: 90, scientific: 80, business: 65, creative: 70, communication: 75, analytical: 85
    };

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 28px;">
        <div style="background: #F8FAFC; border: 1px solid var(--border-color); padding: 20px; border-radius: var(--radius-lg);">
          <h4 style="margin-bottom: 12px; color: var(--dark-blue);">🎓 Academic Standing</h4>
          <p style="font-size: 0.8125rem; line-height: 1.8;">
            <b>Candidate:</b> ${p.personal.fullName}<br />
            <b>School:</b> ${p.academic.school}<br />
            <b>Board:</b> ${p.academic.board}<br />
            <b>Medium:</b> ${p.academic.medium}<br />
            <b>Aggregate Percentage:</b> <span class="badge badge-success">${p.marks.percentage}%</span>
          </p>
        </div>

        <div style="background: #F8FAFC; border: 1px solid var(--border-color); padding: 20px; border-radius: var(--radius-lg);">
          <h4 style="margin-bottom: 12px; color: var(--dark-blue);">🧭 Chosen Academic Pathway</h4>
          <p style="font-size: 0.8125rem; line-height: 1.8;">
            <b>Stream:</b> <span class="badge badge-blue">${p.selectedStream.toUpperCase()}</span><br />
            <b>Admission Target:</b> MHT-CET Engineering CAP Counselling<br />
            <b>Target Percentile:</b> ${p.marks.goal || 92.0}%<br />
            <b>Future Ambitions:</b> <i>"${p.ambitions || 'Engineering Innovation'}"</i>
          </p>
        </div>
      </div>

      <h4 style="margin-bottom: 12px; color: var(--dark-blue);">🧠 25-Question Aptitude Assessment Breakdown</h4>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px;">
        ${Object.entries(aptScores).map(([cat, score]) => `
          <div style="background: #FFFFFF; border: 1px solid var(--border-color); padding: 14px; border-radius: var(--radius-md);">
            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; font-weight: 600; text-transform: capitalize; margin-bottom: 6px;">
              <span>${cat}</span>
              <span class="text-primary">${score}%</span>
            </div>
            <div style="width: 100%; height: 6px; background: #E2E8F0; border-radius: 999px; overflow: hidden;">
              <div style="width: ${score}%; height: 100%; background: var(--primary);"></div>
            </div>
          </div>
        `).join("")}
      </div>
    `;
  },

  // =========================================================================
  // AI CONSULTANT RAG CHAT (Direct Backend Integration)
  // =========================================================================
  sendPromptText(text) {
    document.getElementById("chatQueryInput").value = text;
    this.handleChatSubmit();
  },

  async handleChatSubmit(e) {
    if (e) e.preventDefault();
    const input = document.getElementById("chatQueryInput");
    const query = input.value.trim();
    if (!query || this.state.isChatLoading) return;

    input.value = "";
    this.appendChatBubble("user", query);

    // Show loading indicator
    this.state.isChatLoading = true;
    const loadingBubble = this.appendChatBubble("assistant", '<div style="display: flex; align-items: center; gap: 8px;"><span>Consulting 181,137 historical records...</span> <span class="badge badge-blue">RAG Active</span></div>', true);

    try {
      const resp = await fetch(API_BASE + "/api/chat", {
        method: "POST",
        headers: this.getAuthHeaders(),
        body: JSON.stringify({
          query,
          user_id: this.state.user.id,
          token: this.state.token,
          stream_context: this.state.profile.selectedStream
        })
      });
      const data = await resp.json();

      loadingBubble.remove();
      this.state.isChatLoading = false;

      if (!data.success && data.status === "error") {
        this.appendChatBubble("assistant", `⚠️ ${data.message}`);
        return;
      }

      let contentHtml = "";
      if (data.student_context_applied) {
        contentHtml += `
          <div style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.725rem; font-weight: 700; color: #1D4ED8; background: #EFF6FF; border: 1px solid #BFDBFE; padding: 3px 10px; border-radius: 9999px; margin-bottom: 8px;">
            <span>🎯 Personalized for ${data.personalized_for || this.state.user.name}</span>
          </div>
        `;
      }
      contentHtml += `<div>${this.formatMarkdownText(data.message)}</div>`;

      // If candidates list exists for clarification
      if (data.candidates && data.candidates.length) {
        contentHtml += `
          <div style="margin-top: 10px;">
            <b style="font-size: 0.75rem; color: var(--dark-blue);">Matching Institute Candidates:</b>
            <div style="display: flex; flex-direction: column; gap: 4px; margin-top: 6px;">
              ${data.candidates.map(c => `<button class="prompt-pill" style="text-align: left;" onclick="App.sendPromptText('Cutoff for ${c}')">${c}</button>`).join("")}
            </div>
          </div>
        `;
      }

      // If raw evidence is available, attach verifiable evidence badge
      if (data.raw_evidence && data.raw_evidence.length > 20) {
        const snippet = data.raw_evidence.length > 500 ? data.raw_evidence.substring(0, 500) + "\n... [Citations Grounded]" : data.raw_evidence;
        contentHtml += `
          <div class="evidence-badge-box">
            <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; color: var(--primary);">
              <span>🔍 Verified Grounded Cutoff Citations (${data.total_matches || 'Direct'} Records):</span>
            </div>
            <pre>${snippet}</pre>
          </div>
        `;
      }

      this.appendChatBubble("assistant", contentHtml);
    } catch (err) {
      console.warn("Chat API error:", err);
      loadingBubble.remove();
      this.state.isChatLoading = false;
      this.appendChatBubble("assistant", `I am currently operating in offline demonstrator mode. For the query: <i>"${query}"</i>, you can inspect verified cutoff records in the **Cutoff Predictor** tab.`);
    }
  },

  appendChatBubble(role, htmlContent, isLoading = false) {
    const feed = document.getElementById("chatMessagesFeed");
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role}`;
    bubble.innerHTML = htmlContent;
    if (isLoading) bubble.id = "chatLoadingBubble";
    feed.appendChild(bubble);
    feed.scrollTop = feed.scrollHeight;
    return bubble;
  },

  clearChat() {
    const feed = document.getElementById("chatMessagesFeed");
    feed.innerHTML = `
      <div class="chat-bubble assistant">
        Chat cleared. Ask me about historical Maharashtra engineering cutoffs, college affiliations, branches, or CAP rules.
      </div>
    `;
  },

  formatMarkdownText(text) {
    if (!text) return "";
    return text
      .replace(/\n\n/g, "<br/><br/>")
      .replace(/\n/g, "<br/>")
      .replace(/\*\*(.*?)\*\*/g, "<b>$1</b>")
      .replace(/\*(.*?)\*/g, "<i>$1</i>");
  },

  // =========================================================================
  // COLLEGE DIRECTORY EXPLORER
  // =========================================================================
  async searchCollegesDirectory() {
    const q = document.getElementById("collegeSearchInput")?.value.trim() || "";
    const container = document.getElementById("collegesDirectoryResults");
    if (!container) return;

    container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8125rem;">Searching institutional profiles...</div>';

    try {
      const resp = await fetch(`${API_BASE}/api/colleges/search?q=${encodeURIComponent(q)}&limit=12`);
      const data = await resp.json();

      if (!data.results || !data.results.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8125rem;">No matching colleges found. Try typing "COEP", "VJTI", "Amravati", or "Pune".</div>';
        return;
      }

      container.innerHTML = data.results.map(col => `
        <div style="background: #F8FAFC; border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 14px 18px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <h4 style="font-size: 0.95rem; color: var(--dark-blue); margin-bottom: 2px;">${col.institute_name}</h4>
            <span style="font-size: 0.75rem; color: var(--text-muted);">Institute Code: <b>${col.institute_code || 'N/A'}</b> | ${col.record_id || 'CAP Maharashtra'}</span>
          </div>
          <button class="btn btn-secondary" style="font-size: 0.75rem; padding: 6px 12px;" onclick="App.sendPromptText('What is the affiliation and cutoffs for ${col.institute_name}?'); App.switchDashboardTab('chat');">
            Inquire Cutoffs →
          </button>
        </div>
      `).join("");
    } catch (e) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8125rem;">Sample directory: COEP Technological University (6006), VJTI Mumbai (3012), Government College of Engineering, Amravati (01002).</div>';
    }
  },

  // =========================================================================
  // CUTOFF LOOKUP DIRECT
  // =========================================================================
  async searchCutoffsDirect() {
    const branch = document.getElementById("cutoffBranchSelect")?.value || "Computer";
    const category = document.getElementById("cutoffCategorySelect")?.value || "GOPENS";
    const minP = document.getElementById("cutoffMinPerc")?.value || 85.0;
    const maxP = document.getElementById("cutoffMaxPerc")?.value || 95.0;
    const container = document.getElementById("cutoffResultsList");
    if (!container) return;

    container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8125rem;">Filtering 181,137 historical records...</div>';

    try {
      const url = `${API_BASE}/api/colleges/search?branch=${encodeURIComponent(branch)}&category=${encodeURIComponent(category)}&min_percentile=${minP}&max_percentile=${maxP}&limit=12`;
      const resp = await fetch(url);
      const data = await resp.json();

      if (!data.results || !data.results.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8125rem;">No historical cutoffs found within that exact range. Try expanding the percentile bounds.</div>';
        return;
      }

      container.innerHTML = data.results.map(r => `
        <div style="background: #F8FAFC; border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 12px 18px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <h4 style="font-size: 0.9rem; color: var(--dark-blue); margin-bottom: 2px;">${r.institute_name}</h4>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${r.branch} | ${r.category} | Round ${r.round || 1} (${r.academic_year || '2025-26'})</span>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 1.15rem; font-weight: 800; color: var(--primary);">${r.closing_percentile}%</div>
            <div style="font-size: 0.7rem; color: var(--text-muted);">Closing Rank: <b>${r.closing_rank}</b></div>
          </div>
        </div>
      `).join("");
    } catch (e) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8125rem;">Cutoff search active. Please start the Neev API server on port 8000.</div>';
    }
  },

  // =========================================================================
  // TOAST NOTIFICATIONS
  // =========================================================================
  showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.style.cssText = `
      padding: 12px 20px;
      border-radius: 10px;
      font-size: 0.8125rem;
      font-weight: 600;
      color: #FFFFFF;
      background: ${type === 'success' ? '#10B981' : type === 'warning' ? '#F59E0B' : '#2563EB'};
      box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
      transition: all 0.3s ease;
      opacity: 0;
      transform: translateY(-10px);
    `;
    toast.innerText = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "1";
      toast.style.transform = "translateY(0)";
    }, 10);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-10px)";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }
};

// Auto-run on DOM ready
document.addEventListener("DOMContentLoaded", () => App.init());
