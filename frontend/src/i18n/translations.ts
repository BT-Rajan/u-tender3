export interface Dictionary {
  onboarding: Record<string, string>;
  common: { loading: string; save: string; cancel: string; back: string };
  whatsapp: { title: string; body: string; cta: string };
  errors: { notFoundTitle: string; notFoundBody: string; goHome: string; crashTitle: string; crashBody: string; reload: string };
  brand: { tagline: string };
  history: { title: string; empty: string; back: string; action: string; by: string; when: string; reason: string; changed: string; link: string; system: string; loadError: string };
  home: { login: string; signup: string; heroTitle: string; heroBody: string; statOpen: string; statContractors: string; statAwarded: string; featuresTitle: string; feature1Title: string; feature1Body: string; feature2Title: string; feature2Body: string; feature3Title: string; feature3Body: string; howTitle: string; step1: string; step2: string; step3: string; whatsappTitle: string; whatsappBody: string; qrAlt: string };
  header: { logOut: string; account: string };
  language: { label: string; en: string; ar: string };
  auth: {
    login: {
      heading: string;
      email: string;
      password: string;
      submit: string;
      submitting: string;
      noAccount: string;
      signupLink: string;
      forgotPassword: string;
      genericError: string;
    };
    signup: {
      heading: string;
      iAmA: string;
      propertyOwner: string;
      contractor: string;
      companyName: string;
      companyNameHint: string;
      fullName: string;
      email: string;
      password: string;
      submit: string;
      submitting: string;
      haveAccount: string;
      loginLink: string;
      genericError: string;
    };
    forgotPassword: {
      heading: string;
      description: string;
      email: string;
      submit: string;
      submitting: string;
      sent: string;
      backToLogin: string;
    };
    resetPassword: {
      heading: string;
      newPassword: string;
      submit: string;
      submitting: string;
      success: string;
      invalidToken: string;
      goToLogin: string;
      requestNew: string;
      missingToken: string;
    };
    verifyEmail: {
      heading: string;
      success: string;
      invalidToken: string;
      continue: string;
      missingToken: string;
    };
    changePassword: {
      heading: string;
      currentPassword: string;
      newPassword: string;
      submit: string;
      submitting: string;
      success: string;
    };
    emailVerifyBanner: { message: string; resend: string; sent: string };
  };
  clarifications: {
    heading: string;
    noQuestions: string;
    sealedBidder: string;
    privateTag: string;
    writeAnswerPlaceholder: string;
    answerButton: string;
    awaitingAnswer: string;
    shareCheckboxLabel: string;
    askPlaceholder: string;
    askButton: string;
    askError: string;
    answerError: string;
  };
  contractor: {
    roleLabel: string;
    dashboard: {
      kpiActiveBids: string;
      kpiProjectsWon: string;
      kpiTotalBids: string;
      myBids: string;
      browseOpenProjects: string;
      noBidsYetPrefix: string;
      banner: {
        documentsIncompleteTitle: string;
        documentsIncompleteBody: string;
        documentsIncompleteCta: string;
        submittedTitle: string;
        submittedBody: string;
        submittedCta: string;
        changesRequestedTitle: string;
        changesRequestedBody: string;
        changesRequestedCta: string;
        paymentRequiredTitle: string;
        paymentRequiredBody: string;
        paymentRequiredCta: string;
        suspendedTitle: string;
        suspendedBody: string;
      };
    };
    feed: {
      eyebrow: string;
      heading: string;
      sortedNewest: string;
      sortedClosest: string;
      subscribeBanner: string;
      viewPlans: string;
      searchPlaceholder: string;
      allTrades: string;
      sortClosest: string;
      sortNewest: string;
      noMatch: string;
      noOpenProjects: string;
      deadline: string;
      offersSoFar: string;
      trade: string;
      bidPlaced: string;
      lockedTitle: string;
      lockedDescription: string;
    };
    status: {
      suspendedTitle: string;
      suspendedBody: string;
      approvedTitle: string;
      approvedBody: string;
      eyebrow: string;
      heading: string;
      changesRequestedTitle: string;
      underReviewTitle: string;
      submittedOn: string;
      pending: string;
      actionNeeded: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      adminNote: string;
      reupload: string;
      upload: string;
      footerNote: string;
    };
    verify: {
      eyebrow: string;
      heading: string;
      description: string;
      companyName: string;
      licenseNumber: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      submitting: string;
      submit: string;
      uploadError: string;
      submitError: string;
    };
    offer: {
      deadlineLabel: string;
      closed: string;
      scope: string;
      drawings: string;
      downloadZip: string;
      noDrawings: string;
      biddingClosedNotice: string;
      yourFinalOffer: string;
      awardedTo: string;
      anotherContractor: string;
      noAwardNotice: string;
      bidAmount: string;
      timeline: string;
      timelinePlaceholder: string;
      messageToOwner: string;
      messagePlaceholder: string;
      updateOffer: string;
      submitOffer: string;
      withdraw: string;
      withdrawing: string;
      tipsHeading: string;
      tip1: string;
      tip2: string;
      tip3: string;
      withdrawError: string;
      submitError: string;
      notAvailableNotice: string;
    };
  };
  owner: {
    roleLabel: string;
    dashboard: {
      statusAll: string;
      statusDraft: string;
      statusOpen: string;
      statusAwaitingReview: string;
      statusUnderEvaluation: string;
      statusAwarded: string;
      statusNoAward: string;
      statusCanceled: string;
      statusExpired: string;
      eyebrow: string;
      heading: string;
      newProject: string;
      kpiOpen: string;
      kpiAwaitingReview: string;
      kpiUnderEvaluation: string;
      kpiAwarded: string;
      kpiTotalOffers: string;
      emptyStatePrefix: string;
      emptyStateLink: string;
      emptyStateSuffix: string;
      searchPlaceholder: string;
      allTenderTypes: string;
      sealed: string;
      ownerVisible: string;
      noMatch: string;
      nothingHere: string;
      offersReceived: string;
      readyToReview: string;
      deadline: string;
      trade: string;
      posted: string;
    };
    projectNew: {
      eyebrow: string;
      heading: string;
      description: string;
      tenderType: string;
      ownerVisibleToggle: string;
      sealedToggle: string;
      ownerVisibleHint: string;
      sealedHint: string;
      title: string;
      titlePlaceholder: string;
      address: string;
      addressPlaceholder: string;
      trade: string;
      tradePlaceholder: string;
      scope: string;
      scopePlaceholder: string;
      drawings: string;
      drawingsHint: string;
      drawingsAccessNote: string;
      deadline: string;
      deadlineNote: string;
      postProject: string;
      posting: string;
      saveAsDraft: string;
      draftNote: string;
      sidebarHeading: string;
      tip1: string;
      tip2: string;
      tip3: string;
      validationError: string;
      submitError: string;
    };
    projectDetail: {
      reviewOffers: string;
      sealedBadge: string;
      ownerVisibleBadge: string;
      publish: string;
      closeEarly: string;
      startEvaluation: string;
      markNoAward: string;
      cancelProject: string;
      noDrawings: string;
      downloadZip: string;
      hideHistory: string;
      viewHistory: string;
      noHistory: string;
      current: string;
      view: string;
      addDrawings: string;
      zipHint: string;
      scope: string;
      lowestBid: string;
      averageBid: string;
      highestBid: string;
      sealedBidsReceived: string;
      sealedExplanation: string;
      noOffersYet: string;
      contractorCol: string;
      ratingCol: string;
      bidCol: string;
      timelineCol: string;
      revisedSuffix: string;
      approve: string;
      closeToAwardHint: string;
      contractorReply: string;
      noReply: string;
      revisionHistory: string;
      rateContractor: string;
      theContractor: string;
      submittedOn: string;
      ratingPlaceholder: string;
      submitReview: string;
      approveError: string;
      drawingsError: string;
      reviewError: string;
      statusError: string;
    };
    verify: {
      eyebrow: string;
      heading: string;
      description: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      submitting: string;
      submit: string;
      uploadError: string;
      submitError: string;
    };
    status: {
      suspendedTitle: string;
      suspendedBody: string;
      approvedTitle: string;
      approvedBody: string;
      eyebrow: string;
      heading: string;
      changesRequestedTitle: string;
      underReviewTitle: string;
      submittedOn: string;
      pending: string;
      actionNeeded: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      adminNote: string;
      reupload: string;
      upload: string;
      footerNote: string;
    };
  };
  admin: {
    nav: {
      requirements: string;
      review: string;
      contractors: string;
      owners: string;
      offers: string;
      projects: string;
      cms: string;
    };
    owners: {
      eyebrow: string;
      heading: string;
      total: string;
      empty: string;
      name: string;
      status: string;
      projects: string;
      manage: string;
    };
    ownerDetail: {
      docReviewError: string;
      approveError: string;
      rejectError: string;
      suspendError: string;
      deleteError: string;
      suspended: string;
      documentsHeading: string;
      document: string;
      statusCol: string;
      approve: string;
      reject: string;
      applicationHeading: string;
      currentStatus: string;
      approveApplication: string;
      requestChanges: string;
      accessHeading: string;
      reactivate: string;
      suspend: string;
      suspendedNote: string;
      suspendNote: string;
      dangerZone: string;
      deleteBlockedNote: string;
      deleteNote: string;
      deleteConfirm: string;
      deleteAccount: string;
      projectsHeading: string;
      noProjects: string;
      projectTitleCol: string;
      projectStatusCol: string;
      projectOffersCol: string;
      viewProject: string;
    };
    offers: {
      eyebrow: string;
      heading: string;
      total: string;
      empty: string;
      project: string;
      contractor: string;
      amount: string;
      status: string;
      tenderType: string;
      submitted: string;
      revised: string;
      suspendedBadge: string;
      viewProject: string;
    };
    projects: {
      eyebrow: string;
      heading: string;
      total: string;
      empty: string;
      owner: string;
      title: string;
      status: string;
      offers: string;
      suspendedBadge: string;
      manage: string;
    };
    projectDetail: {
      eyebrow: string;
      suspended: string;
      editHeading: string;
      titleLabel: string;
      addressLabel: string;
      descriptionLabel: string;
      tradeLabel: string;
      deadlineLabel: string;
      saveChanges: string;
      saveError: string;
      accessHeading: string;
      reactivate: string;
      suspend: string;
      suspendedNote: string;
      suspendNote: string;
      suspendError: string;
      dangerZone: string;
      deleteBlockedNote: string;
      deleteNote: string;
      deleteConfirm: string;
      deleteProject: string;
      deleteError: string;
      offersHeading: string;
      noOffers: string;
      contractorCol: string;
      amountCol: string;
      timelineCol: string;
      statusCol: string;
      actionsCol: string;
      edit: string;
      editOfferHeading: string;
      amountFieldLabel: string;
      timelineFieldLabel: string;
      messageFieldLabel: string;
      saveOffer: string;
      cancel: string;
      editOfferError: string;
      suspendOffer: string;
      reactivateOffer: string;
      suspendOfferError: string;
      deleteOffer: string;
      deleteOfferError: string;
      deleteOfferConfirm: string;
      deleteOfferBlocked: string;
      offerSuspendedBadge: string;
    };
    requirements: {
      eyebrow: string;
      heading: string;
      description: string;
      forContractors: string;
      forOwners: string;
      emptyForScope: string;
      toggleRequiredFor: string;
      required: string;
      optional: string;
      removeTitle: string;
      namePlaceholder: string;
      descriptionPlaceholder: string;
      addForOwners: string;
      addForContractors: string;
      addError: string;
      updateError: string;
      removeError: string;
    };
  };
}

export const en: Dictionary = {
  onboarding: {
    trialNote: "Your trial is running. You can send offers without a subscription until",
    dashboardNoMatch: "No bids match this filter. Press the total to see all of them.",
    signupEyebrow: "Contractor sign-up",
    signupHeading: "Create your contractor account",
    signupIntro: "Enter your WhatsApp number. We send a 6-digit code to confirm it.",
    phone: "WhatsApp number",
    phoneHint: "Include the country code, for example 96599444463.",
    sendCode: "Send code",
    sending: "Sending...",
    codeSent: "We sent a code to your WhatsApp. It expires in 5 minutes.",
    changeNumber: "Use a different number",
    code: "Code from WhatsApp",
    fullName: "Your name",
    company: "Company name",
    email: "Email",
    password: "Password",
    passwordHint: "At least 8 characters.",
    createAccount: "Create account",
    creating: "Creating account...",
    haveAccount: "Already have an account?",
    logIn: "Log in",
    signupError: "We could not create your account. Check the code and try again.",
    joinHeading: "Finish your sign-up",
    joinIntro: "Add your email and a password to finish your account. This link works for 24 hours.",
    joinSubmit: "Save and continue",
    joinSaving: "Saving...",
    joinMissing: "This link is incomplete. Open the link from WhatsApp again.",
    joinError: "This link has expired or was already used. Ask for a new link on WhatsApp.",
    wizardEyebrow: "Onboarding",
    wizardHeading: "Tell us about your business",
    wizardIntro: "We check these details before we activate your account.",
    step1: "Business details",
    step2: "Trades you offer",
    businessName: "Business name",
    address: "Business address",
    website: "Website (optional)",
    websiteHint: "For example www.example.com",
    businessEmail: "Business email",
    registrationId: "Business registration ID",
    tradesHeading: "Choose the trades you offer",
    tradesHint: "Pick at least one.",
    tradesRequired: "Choose at least one trade.",
    next: "Next",
    back: "Back",
    save: "Save and continue",
    saving: "Saving...",
    wizardError: "We could not save your details. Check the form and try again.",
    subEyebrow: "Subscription",
    subHeading: "Choose a plan",
    subIntro: "Your first payment covers the activation fee and the first month. Each later payment covers one more month.",
    activationFee: "Activation fee",
    monthlyFee: "Monthly fee",
    firstPayment: "First payment",
    monthlyPayment: "Monthly payment",
    payWithMyFatoorah: "Pay with MyFatoorah",
    opening: "Opening payment...",
    paidNotice: "Payment received. We are checking your details and aim to activate you within 48 hours.",
    failedNotice: "The payment was not completed. You can try again below.",
    checkingPayment: "Checking your payment...",
    paidUntil: "Paid until",
    invoices: "Payments",
    noInvoices: "No payments yet.",
    statusPending: "Waiting for payment",
    statusPaid: "Paid",
    statusCanceled: "Canceled",
    statusExpired: "Expired",
    continuePayment: "Continue to payment",
    paymentError: "We could not start the payment. Try again.",
    noPlans: "No plans are available yet. Check back soon.",
    panelDetailsTitle: "Next: add your business details",
    panelDetailsBody: "Enter your business details and the trades you offer.",
    panelDetailsCta: "Add details",
    panelSubscribeTitle: "Next: choose a plan",
    panelSubscribeBody: "Pay the activation fee and the first month to continue.",
    panelSubscribeCta: "Choose a plan",
    panelAwaitingTitle: "Payment received",
    panelAwaitingBody: "Our team checks your details and activates your account within 48 hours.",
    panelDueBy: "Activation due by",
    panelOverdue: "Activation is past the 48-hour target. Thank you for your patience.",
    panelActiveTitle: "Your account is active",
    panelActiveBody: "You can send offers on open tenders.",
    forgotCodeSent: "If an account uses this email, we sent a code to its WhatsApp number.",
    forgotCode: "Code from WhatsApp",
    forgotNewPassword: "New password",
    forgotConfirm: "Set new password",
    forgotSaving: "Saving...",
    forgotDone: "Your password is changed. You can log in now.",
    forgotError: "That code is not right or has expired. Ask for a new code.",
    useAnotherEmail: "Use a different email",
  },
  whatsapp: {
    title: "Use U-Tender on WhatsApp",
    body: "Open a chat and send the word utender. We'll reply with your account options.",
    cta: "Open WhatsApp",
  },
  errors: {
    notFoundTitle: "Page not found",
    notFoundBody: "The page you're looking for doesn't exist or has moved.",
    goHome: "Back to home",
    crashTitle: "Something went wrong",
    crashBody: "An unexpected error stopped this page from loading. Reloading usually fixes it.",
    reload: "Reload page",
  },
  common: {
    loading: "Loading…",
    save: "Save",
    cancel: "Cancel",
    back: "Back",
  },
  brand: {
    tagline: "Drawings in. Offers out.",
  },
  history: {
    title: "Account history",
    empty: "Nothing has been recorded for this account yet.",
    back: "Back",
    action: "Action",
    by: "By",
    when: "When",
    reason: "Reason",
    changed: "Changed",
    link: "History",
    system: "System",
    loadError: "The history could not be loaded.",
  },
  home: {
    login: "Log in",
    signup: "Sign up",
    heroTitle: "Tenders, drawings and offers in one place",
    heroBody: "U-Tender connects building owners with verified contractors. Post a tender, share drawings and receive offers, from the website or from WhatsApp.",
    statOpen: "Open tenders",
    statContractors: "Verified contractors",
    statAwarded: "Projects awarded",
    featuresTitle: "Built for trust",
    feature1Title: "Verified contractors",
    feature1Body: "Every contractor's documents are reviewed before they can bid.",
    feature2Title: "Sealed or open bidding",
    feature2Body: "Owners choose whether bidders can see each other's offers.",
    feature3Title: "Works on WhatsApp",
    feature3Body: "Owners and contractors can post, browse and bid from a WhatsApp chat.",
    howTitle: "How it works",
    step1: "Create your account",
    step2: "Post a tender or bid",
    step3: "Award and track",
    whatsappTitle: "Use U-Tender on WhatsApp",
    whatsappBody: "Scan the code with your phone's camera. It opens a chat with U-Tender. Send the word utender to start.",
    qrAlt: "QR code to open U-Tender on WhatsApp",
  },
  header: {
    logOut: "Log out",
    account: "Account",
  },
  language: {
    label: "Language",
    en: "English",
    ar: "العربية",
  },
  auth: {
    login: {
      heading: "Log in",
      email: "Email",
      password: "Password",
      submit: "Log in",
      submitting: "Logging in…",
      noAccount: "No account?",
      signupLink: "Sign up",
      forgotPassword: "Forgot password?",
      genericError: "Invalid email or password.",
    },
    signup: {
      heading: "Create an account",
      iAmA: "I am a...",
      propertyOwner: "Property owner",
      contractor: "Contractor",
      companyName: "Company name",
      companyNameHint: "You'll submit verification documents after signing up.",
      fullName: "Full name",
      email: "Email",
      password: "Password",
      submit: "Create account",
      submitting: "Creating…",
      haveAccount: "Already have an account?",
      loginLink: "Log in",
      genericError: "Could not create account.",
    },
    forgotPassword: {
      heading: "Reset your password",
      description: "Enter your account email and we'll send you a link to reset your password.",
      email: "Email",
      submit: "Send reset link",
      submitting: "Sending…",
      sent: "If an account with that email exists, a reset link has been sent.",
      backToLogin: "Back to log in",
    },
    resetPassword: {
      heading: "Choose a new password",
      newPassword: "New password",
      submit: "Reset password",
      submitting: "Resetting…",
      success: "Your password has been reset. You can now log in.",
      invalidToken: "This reset link is invalid or has expired.",
      goToLogin: "Go to log in",
      requestNew: "Request a new reset link",
      missingToken: "No reset token was provided.",
    },
    verifyEmail: {
      heading: "Verifying your email…",
      success: "Your email address has been verified.",
      invalidToken: "This verification link is invalid or has expired.",
      continue: "Continue",
      missingToken: "No verification token was provided.",
    },
    changePassword: {
      heading: "Change password",
      currentPassword: "Current password",
      newPassword: "New password",
      submit: "Change password",
      submitting: "Changing…",
      success: "Password changed.",
    },
    emailVerifyBanner: {
      message: "Please verify your email address.",
      resend: "Resend verification email",
      sent: "Verification email sent.",
    },
  },
  clarifications: {
    heading: "Questions & answers",
    noQuestions: "No questions yet.",
    sealedBidder: "sealed bidder",
    privateTag: "private",
    writeAnswerPlaceholder: "Write an answer…",
    answerButton: "Answer",
    awaitingAnswer: "Awaiting an answer from the owner.",
    shareCheckboxLabel: "Share this Q&A with other bidders once answered",
    askPlaceholder: "Ask the owner a question about this project…",
    askButton: "Ask",
    askError: "Could not submit your question.",
    answerError: "Could not submit your answer.",
  },
  contractor: {
    roleLabel: "Contractor",
    dashboard: {
      kpiActiveBids: "Active bids",
      kpiProjectsWon: "Projects won",
      kpiTotalBids: "Total bids placed",
      myBids: "My bids",
      browseOpenProjects: "Browse open projects",
      noBidsYetPrefix: "You haven't placed any bids yet.",
      banner: {
        documentsIncompleteTitle: "Finish verifying your company",
        documentsIncompleteBody: "Upload your documents so an admin can review your account.",
        documentsIncompleteCta: "Continue verification",
        submittedTitle: "Application under review",
        submittedBody: "An admin is reviewing your documents. We'll notify you once a decision is made.",
        submittedCta: "View submission",
        changesRequestedTitle: "Changes requested",
        changesRequestedBody: "One or more documents need to be re-uploaded before your account can be approved.",
        changesRequestedCta: "Review and re-upload",
        paymentRequiredTitle: "Subscribe to unlock bidding",
        paymentRequiredBody: "You're verified — subscribe to view drawings and submit offers.",
        paymentRequiredCta: "View plans",
        suspendedTitle: "Account suspended",
        suspendedBody: "Your account has been suspended by a site admin. Contact support if you believe this is a mistake.",
      },
    },
    feed: {
      eyebrow: "Contractor · Open projects",
      heading: "Projects open for bidding",
      sortedNewest: "Sorted by most recently posted.",
      sortedClosest: "Sorted by closing soonest.",
      subscribeBanner: "You're approved, but drawings and offers stay locked until you subscribe.",
      viewPlans: "View plans",
      searchPlaceholder: "Search title, address, or scope…",
      allTrades: "All trades",
      sortClosest: "Closing soonest",
      sortNewest: "Newest first",
      noMatch: "No projects match your filters.",
      noOpenProjects: "No open projects right now. Check back soon.",
      deadline: "Deadline",
      offersSoFar: "Offers so far",
      trade: "Trade",
      bidPlaced: "Bid placed",
      lockedTitle: "Subscribe to view drawings",
      lockedDescription: "Unlock full drawings, scope details, and the ability to submit offers.",
    },
    status: {
      suspendedTitle: "Account suspended",
      suspendedBody:
        "Your account has been suspended by a site admin. You can't view new projects or submit offers while suspended. Contact support if you believe this is a mistake.",
      approvedTitle: "You're approved",
      approvedBody: "Head to your dashboard to browse open projects.",
      eyebrow: "Contractor · Account verification",
      heading: "Application status",
      changesRequestedTitle: "Changes requested — one or more documents need to be re-uploaded",
      underReviewTitle: "Application under review",
      submittedOn: "Submitted",
      pending: "Pending",
      actionNeeded: "Action needed",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      adminNote: "Admin note:",
      reupload: "Re-upload",
      upload: "Upload",
      footerNote:
        "You'll be notified as soon as your account is fully approved. Full access to drawings and offers stays locked until then.",
    },
    verify: {
      eyebrow: "Contractor · Account verification",
      heading: "Verify your company",
      description: "Submit the documents below so a site admin can activate your account.",
      companyName: "Company name",
      licenseNumber: "License number",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      submitting: "Submitting…",
      submit: "Submit for review",
      uploadError: "Could not upload document.",
      submitError: "Could not submit for review.",
    },
    offer: {
      deadlineLabel: "Deadline",
      closed: "Closed",
      scope: "Scope",
      drawings: "Drawings",
      downloadZip: "Download all as .zip",
      noDrawings: "No drawings were uploaded for this project.",
      biddingClosedNotice: "Bidding on this project has closed.",
      yourFinalOffer: "Your final offer:",
      awardedTo: "Awarded to",
      anotherContractor: "another contractor",
      noAwardNotice: "The owner decided not to award this project.",
      bidAmount: "Your bid amount (USD)",
      timeline: "Estimated timeline",
      timelinePlaceholder: "e.g. 3 weeks from start",
      messageToOwner: "Message to owner",
      messagePlaceholder: "Outline your approach, materials, and anything the drawings don't cover.",
      updateOffer: "Update offer",
      submitOffer: "Submit offer",
      withdraw: "Withdraw offer",
      withdrawing: "Withdrawing…",
      tipsHeading: "Tips for winning bids",
      tip1: "Reference specific details from the drawings — it signals you reviewed them closely.",
      tip2: "Owners can see your rating and past reviews next to your bid.",
      tip3: "You can revise your offer any time before the deadline.",
      withdrawError: "Could not withdraw offer.",
      submitError: "Could not submit offer.",
      notAvailableNotice: "That project isn't available to you right now.",
    },
  },
  owner: {
    roleLabel: "Owner",
    dashboard: {
      statusAll: "All statuses",
      statusDraft: "Draft",
      statusOpen: "Open",
      statusAwaitingReview: "Awaiting review",
      statusUnderEvaluation: "Under evaluation",
      statusAwarded: "Awarded",
      statusNoAward: "No award",
      statusCanceled: "Canceled",
      statusExpired: "Expired",
      eyebrow: "Owner dashboard",
      heading: "Your projects",
      newProject: "+ New project",
      kpiOpen: "Open",
      kpiAwaitingReview: "Awaiting review",
      kpiUnderEvaluation: "Under evaluation",
      kpiAwarded: "Awarded",
      kpiTotalOffers: "Total offers",
      emptyStatePrefix: "You haven't posted a project yet.",
      emptyStateLink: "Post your first one",
      emptyStateSuffix: "to start receiving offers.",
      searchPlaceholder: "Search title or address…",
      allTenderTypes: "All tender types",
      sealed: "Sealed",
      ownerVisible: "Owner-visible",
      noMatch: "No projects match your filters.",
      nothingHere: "Nothing here.",
      offersReceived: "offer(s) received",
      readyToReview: "ready to review",
      deadline: "Deadline",
      trade: "Trade",
      posted: "Posted",
    },
    projectNew: {
      eyebrow: "New project",
      heading: "Post a project",
      description: "Add your drawings and set a deadline — contractors can only bid before it closes.",
      tenderType: "Tender type",
      ownerVisibleToggle: "Owner-visible",
      sealedToggle: "Sealed",
      ownerVisibleHint: "You can see bids as they come in. Locked in once the first bid arrives.",
      sealedHint: "Bids stay hidden from you until bidding closes. Locked in once the first bid arrives.",
      title: "Project title",
      titlePlaceholder: "e.g. Maple St. Duplex — Roof Replacement",
      address: "Site address",
      addressPlaceholder: "Street, city, state",
      trade: "Trade",
      tradePlaceholder: "e.g. Roofing, Framing, Fencing",
      scope: "Scope of work",
      scopePlaceholder: "Describe the work you need done. Contractors will use this alongside your drawings to price their offer.",
      drawings: "Drawings",
      drawingsHint: "PDF, DWG, JPG, PNG, or a .zip folder of drawings — up to 50MB total",
      drawingsAccessNote: "Only approved, subscribed contractors can view these files.",
      deadline: "Bid deadline",
      deadlineNote: "No offers are accepted after this time.",
      postProject: "Post project",
      posting: "Posting…",
      saveAsDraft: "Save as draft",
      draftNote: "A draft is only visible to you. Publish it later from the project page when you're ready for bids.",
      sidebarHeading: "Before you post",
      tip1: "Clear drawings get more accurate offers — include dimensions where you can.",
      tip2: "Give contractors at least 5–7 days to price the job properly.",
      tip3: "You won't be charged. Posting and reviewing offers is free for property owners.",
      validationError: "Title, address, and deadline are required.",
      submitError: "Could not create project.",
    },
    projectDetail: {
      reviewOffers: "Review offers",
      sealedBadge: "Sealed",
      ownerVisibleBadge: "Owner-visible",
      publish: "Publish — start accepting bids",
      closeEarly: "Close bidding early",
      startEvaluation: "Start evaluation",
      markNoAward: "Mark no award",
      cancelProject: "Cancel project",
      noDrawings: "No drawings uploaded yet",
      downloadZip: "Download all as .zip",
      hideHistory: "Hide revision history",
      viewHistory: "View revision history",
      noHistory: "No revision history yet.",
      current: "(current)",
      view: "view",
      addDrawings: "Add drawings",
      zipHint: "You can also upload a .zip folder of drawings.",
      scope: "Scope",
      lowestBid: "Lowest bid",
      averageBid: "Average bid",
      highestBid: "Highest bid",
      sealedBidsReceived: "sealed bid(s) received",
      sealedExplanation:
        "This is a sealed tender — bidder identities and amounts stay hidden from you until bidding closes. Close bidding to reveal and evaluate them.",
      noOffersYet: "No offers yet. Contractors can bid until the deadline above.",
      contractorCol: "Contractor",
      ratingCol: "Rating",
      bidCol: "Bid",
      timelineCol: "Timeline",
      revisedSuffix: "revised x",
      approve: "Approve",
      closeToAwardHint: "Close bidding to award",
      contractorReply: "Contractor's reply",
      noReply: "No reply message.",
      revisionHistory: "Revision history",
      rateContractor: "Rate",
      theContractor: "the contractor",
      submittedOn: "Submitted",
      ratingPlaceholder: "How did the work go? Optional, but helps other owners.",
      submitReview: "Submit review",
      approveError: "Could not approve this offer.",
      drawingsError: "Could not add drawings.",
      reviewError: "Could not submit review.",
      statusError: "Could not update this project's status.",
    },
    verify: {
      eyebrow: "Owner · Account verification",
      heading: "Verify your account",
      description: "Submit the documents below so a site admin can activate your account.",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      submitting: "Submitting…",
      submit: "Submit for review",
      uploadError: "Could not upload document.",
      submitError: "Could not submit for review.",
    },
    status: {
      suspendedTitle: "Account suspended",
      suspendedBody:
        "Your account has been suspended by a site admin. You can't post or manage projects while suspended. Contact support if you believe this is a mistake.",
      approvedTitle: "You're approved",
      approvedBody: "Head to your dashboard to post a project.",
      eyebrow: "Owner · Account verification",
      heading: "Application status",
      changesRequestedTitle: "Changes requested — one or more documents need to be re-uploaded",
      underReviewTitle: "Application under review",
      submittedOn: "Submitted",
      pending: "Pending",
      actionNeeded: "Action needed",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      adminNote: "Admin note:",
      reupload: "Re-upload",
      upload: "Upload",
      footerNote:
        "You'll be notified as soon as your account is fully approved. Posting and managing projects stays locked until then.",
    },
  },
  admin: {
    nav: {
      requirements: "Document requirements",
      review: "Review applications",
      contractors: "All contractors",
      owners: "All owners",
      offers: "All offers",
      projects: "All projects",
      cms: "Website content",
    },
    owners: {
      eyebrow: "Admin · Owners",
      heading: "All property owners",
      total: "total",
      empty: "No owners have signed up yet.",
      name: "Name",
      status: "Status",
      projects: "Projects",
      manage: "Manage",
    },
    ownerDetail: {
      docReviewError: "Could not update this document.",
      approveError: "Could not approve this owner.",
      rejectError: "Could not request changes.",
      suspendError: "Could not update account access.",
      deleteError: "Could not delete this owner.",
      suspended: "Suspended",
      documentsHeading: "Verification documents",
      document: "Document",
      statusCol: "Status",
      approve: "Approve",
      reject: "Reject",
      applicationHeading: "Application",
      currentStatus: "Current status",
      approveApplication: "Approve owner",
      requestChanges: "Request changes",
      accessHeading: "Account access",
      reactivate: "Reactivate account",
      suspend: "Suspend account",
      suspendedNote: "This owner can't post or manage projects until reactivated.",
      suspendNote: "Immediately blocks the owner from posting or managing projects, without deleting anything.",
      dangerZone: "Danger zone",
      deleteBlockedNote:
        "This owner has posted projects. Suspend the account instead of deleting it, to keep that project and offer history intact for the contractors involved.",
      deleteNote: "This owner has no projects yet, so deleting removes the account entirely. This can't be undone.",
      deleteConfirm: "Permanently delete this owner's account? This can't be undone.",
      deleteAccount: "Delete account",
      projectsHeading: "Projects posted",
      noProjects: "This owner hasn't posted any projects yet.",
      projectTitleCol: "Project",
      projectStatusCol: "Status",
      projectOffersCol: "Offers",
      viewProject: "View",
    },
    offers: {
      eyebrow: "Admin · Offers",
      heading: "All offers",
      total: "total",
      empty: "No offers have been submitted yet.",
      project: "Project",
      contractor: "Contractor",
      amount: "Amount",
      status: "Status",
      tenderType: "Tender type",
      submitted: "Submitted",
      revised: "revised",
      suspendedBadge: "Offer suspended",
      viewProject: "View full project",
    },
    projects: {
      eyebrow: "Admin · Projects",
      heading: "All projects",
      total: "total",
      empty: "No projects have been posted yet.",
      owner: "Owner",
      title: "Project",
      status: "Status",
      offers: "Offers",
      suspendedBadge: "Suspended",
      manage: "Manage",
    },
    projectDetail: {
      eyebrow: "Admin · Projects",
      suspended: "Suspended",
      editHeading: "Project details",
      titleLabel: "Title",
      addressLabel: "Address",
      descriptionLabel: "Scope",
      tradeLabel: "Trade",
      deadlineLabel: "Bid deadline",
      saveChanges: "Save changes",
      saveError: "Could not save changes.",
      accessHeading: "Marketplace visibility",
      reactivate: "Reactivate project",
      suspend: "Suspend project",
      suspendedNote: "This project is hidden from the contractor feed and can't receive new offers until reactivated.",
      suspendNote: "Immediately hides this project from the contractor feed and blocks new offers, without deleting anything.",
      suspendError: "Could not update project visibility.",
      dangerZone: "Danger zone",
      deleteBlockedNote:
        "This project has offers on it. Suspend it instead of deleting it, to keep that bid history intact for the contractors involved.",
      deleteNote: "This project has no offers yet, so deleting removes it entirely. This can't be undone.",
      deleteConfirm: "Permanently delete this project? This can't be undone.",
      deleteProject: "Delete project",
      deleteError: "Could not delete this project.",
      offersHeading: "Offers on this project",
      noOffers: "No offers have been submitted on this project.",
      contractorCol: "Contractor",
      amountCol: "Amount",
      timelineCol: "Timeline",
      statusCol: "Status",
      actionsCol: "",
      edit: "Edit",
      editOfferHeading: "Edit offer",
      amountFieldLabel: "Amount (USD)",
      timelineFieldLabel: "Timeline",
      messageFieldLabel: "Message",
      saveOffer: "Save",
      cancel: "Cancel",
      editOfferError: "Could not save this offer.",
      suspendOffer: "Suspend",
      reactivateOffer: "Reactivate",
      suspendOfferError: "Could not update this offer.",
      deleteOffer: "Delete",
      deleteOfferError: "Could not delete this offer.",
      deleteOfferConfirm: "Permanently delete this offer? This can't be undone.",
      deleteOfferBlocked: "This offer was awarded — suspend it instead of deleting it.",
      offerSuspendedBadge: "Offer suspended",
    },
    requirements: {
      eyebrow: "Admin · Document requirements",
      heading: "Required documents",
      description:
        "Turn requirements on or off, or remove one entirely. Changes apply to new submissions right away — accounts already approved aren't affected.",
      forContractors: "For contractors",
      forOwners: "For owners",
      emptyForScope: "No requirements set up for this group yet.",
      toggleRequiredFor: "Toggle required for",
      required: "Required",
      optional: "Optional",
      removeTitle: "Remove requirement",
      namePlaceholder: "Document name, e.g. Civil ID",
      descriptionPlaceholder: "Short description shown to the applicant",
      addForOwners: "+ Add owner requirement",
      addForContractors: "+ Add contractor requirement",
      addError: "Could not add requirement.",
      updateError: "Could not update requirement.",
      removeError: "Could not remove requirement.",
    },
  },
};

export const ar: Dictionary = {
  onboarding: {
    trialNote: "تجربتك مفعّلة. يمكنك تقديم العروض دون اشتراك حتى",
    dashboardNoMatch: "لا توجد عروض تطابق هذا الفلتر. اضغط على الإجمالي لعرض الكل.",
    signupEyebrow: "تسجيل مقاول",
    signupHeading: "أنشئ حساب المقاول",
    signupIntro: "أدخل رقم واتساب الخاص بك. سنرسل رمزاً من 6 أرقام لتأكيده.",
    phone: "رقم واتساب",
    phoneHint: "أدخل رمز الدولة، مثال 96599444463.",
    sendCode: "أرسل الرمز",
    sending: "جارٍ الإرسال...",
    codeSent: "أرسلنا رمزاً إلى واتساب الخاص بك. ينتهي خلال 5 دقائق.",
    changeNumber: "استخدم رقماً آخر",
    code: "الرمز المرسل على واتساب",
    fullName: "اسمك",
    company: "اسم الشركة",
    email: "البريد الإلكتروني",
    password: "كلمة المرور",
    passwordHint: "8 أحرف على الأقل.",
    createAccount: "إنشاء الحساب",
    creating: "جارٍ إنشاء الحساب...",
    haveAccount: "لديك حساب بالفعل؟",
    logIn: "تسجيل الدخول",
    signupError: "تعذر إنشاء الحساب. تحقق من الرمز وحاول مرة أخرى.",
    joinHeading: "أكمل التسجيل",
    joinIntro: "أضف بريدك الإلكتروني وكلمة مرور لإكمال حسابك. هذا الرابط صالح لمدة 24 ساعة.",
    joinSubmit: "حفظ والمتابعة",
    joinSaving: "جارٍ الحفظ...",
    joinMissing: "الرابط غير مكتمل. افتح الرابط من واتساب مرة أخرى.",
    joinError: "انتهت صلاحية هذا الرابط أو تم استخدامه. اطلب رابطاً جديداً عبر واتساب.",
    wizardEyebrow: "التسجيل",
    wizardHeading: "أخبرنا عن شركتك",
    wizardIntro: "نتحقق من هذه البيانات قبل تفعيل حسابك.",
    step1: "بيانات الشركة",
    step2: "التخصصات التي تقدمها",
    businessName: "اسم الشركة",
    address: "عنوان الشركة",
    website: "الموقع الإلكتروني (اختياري)",
    websiteHint: "مثال www.example.com",
    businessEmail: "البريد الإلكتروني للشركة",
    registrationId: "رقم السجل التجاري",
    tradesHeading: "اختر التخصصات التي تقدمها",
    tradesHint: "اختر تخصصاً واحداً على الأقل.",
    tradesRequired: "اختر تخصصاً واحداً على الأقل.",
    next: "التالي",
    back: "رجوع",
    save: "حفظ والمتابعة",
    saving: "جارٍ الحفظ...",
    wizardError: "تعذر حفظ البيانات. تحقق من النموذج وحاول مرة أخرى.",
    subEyebrow: "الاشتراك",
    subHeading: "اختر خطة",
    subIntro: "تغطي دفعتك الأولى رسوم التفعيل والشهر الأول. كل دفعة لاحقة تغطي شهراً إضافياً.",
    activationFee: "رسوم التفعيل",
    monthlyFee: "الرسوم الشهرية",
    firstPayment: "الدفعة الأولى",
    monthlyPayment: "الدفعة الشهرية",
    payWithMyFatoorah: "الدفع عبر MyFatoorah",
    opening: "جارٍ فتح صفحة الدفع...",
    paidNotice: "تم استلام الدفع. نتحقق من بياناتك ونهدف إلى تفعيل حسابك خلال 48 ساعة.",
    failedNotice: "لم يكتمل الدفع. يمكنك المحاولة مرة أخرى.",
    checkingPayment: "جارٍ التحقق من الدفع...",
    paidUntil: "مدفوع حتى",
    invoices: "المدفوعات",
    noInvoices: "لا توجد مدفوعات بعد.",
    statusPending: "بانتظار الدفع",
    statusPaid: "مدفوع",
    statusCanceled: "ملغى",
    statusExpired: "منتهي",
    continuePayment: "المتابعة للدفع",
    paymentError: "تعذر بدء الدفع. حاول مرة أخرى.",
    noPlans: "لا توجد خطط متاحة حالياً. تحقق لاحقاً.",
    panelDetailsTitle: "الخطوة التالية: أضف بيانات شركتك",
    panelDetailsBody: "أدخل بيانات شركتك والتخصصات التي تقدمها.",
    panelDetailsCta: "أضف البيانات",
    panelSubscribeTitle: "الخطوة التالية: اختر خطة",
    panelSubscribeBody: "ادفع رسوم التفعيل والشهر الأول للمتابعة.",
    panelSubscribeCta: "اختر خطة",
    panelAwaitingTitle: "تم استلام الدفع",
    panelAwaitingBody: "يتحقق فريقنا من بياناتك ويفعل حسابك خلال 48 ساعة.",
    panelDueBy: "موعد التفعيل",
    panelOverdue: "تجاوز التفعيل الموعد المستهدف وهو 48 ساعة. نشكرك على صبرك.",
    panelActiveTitle: "حسابك مفعّل",
    panelActiveBody: "يمكنك تقديم العروض على المناقصات المفتوحة.",
    forgotCodeSent: "إذا كان هناك حساب يستخدم هذا البريد، أرسلنا رمزاً إلى رقم واتساب المرتبط به.",
    forgotCode: "الرمز المرسل على واتساب",
    forgotNewPassword: "كلمة المرور الجديدة",
    forgotConfirm: "تعيين كلمة المرور الجديدة",
    forgotSaving: "جارٍ الحفظ...",
    forgotDone: "تم تغيير كلمة المرور. يمكنك تسجيل الدخول الآن.",
    forgotError: "الرمز غير صحيح أو انتهت صلاحيته. اطلب رمزاً جديداً.",
    useAnotherEmail: "استخدم بريداً آخر",
  },
  whatsapp: {
    title: "استخدم يو-تندر عبر واتساب",
    body: "افتح محادثة وأرسل كلمة utender. سنرد عليك بخيارات حسابك.",
    cta: "فتح واتساب",
  },
  errors: {
    notFoundTitle: "الصفحة غير موجودة",
    notFoundBody: "الصفحة التي تبحث عنها غير موجودة أو تم نقلها.",
    goHome: "العودة إلى الرئيسية",
    crashTitle: "حدث خطأ ما",
    crashBody: "أوقف خطأ غير متوقع تحميل هذه الصفحة. عادةً ما تحل إعادة التحميل المشكلة.",
    reload: "إعادة تحميل الصفحة",
  },
  common: {
    loading: "جارٍ التحميل…",
    save: "حفظ",
    cancel: "إلغاء",
    back: "رجوع",
  },
  brand: {
    tagline: "المخططات تدخل، والعروض تخرج.",
  },
  history: {
    title: "سجل الحساب",
    empty: "لم يُسجَّل أي نشاط لهذا الحساب بعد.",
    back: "رجوع",
    action: "الإجراء",
    by: "بواسطة",
    when: "التاريخ",
    reason: "السبب",
    changed: "التغيير",
    link: "السجل",
    system: "النظام",
    loadError: "تعذر تحميل السجل.",
  },
  home: {
    login: "تسجيل الدخول",
    signup: "إنشاء حساب",
    heroTitle: "Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ§Øª ÙˆØ§Ù„Ù…Ø®Ø·Ø·Ø§Øª ÙˆØ§Ù„Ø¹Ø±ÙˆØ¶ ÙÙŠ Ù…ÙƒØ§Ù† ÙˆØ§Ø­Ø¯",
    heroBody: "ÙŠØ±Ø¨Ø· U-Tender Ø£ØµØ­Ø§Ø¨ Ø§Ù„Ù…Ø¨Ø§Ù†ÙŠ Ø¨Ø§Ù„Ù…Ù‚Ø§ÙˆÙ„ÙŠÙ† Ø§Ù„Ù…Ø¹ØªÙ…Ø¯ÙŠÙ†. Ø§Ù†Ø´Ø± Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ© ÙˆØ´Ø§Ø±Ùƒ Ø§Ù„Ù…Ø®Ø·Ø·Ø§Øª ÙˆØ§Ø³ØªÙ‚Ø¨Ù„ Ø§Ù„Ø¹Ø±ÙˆØ¶ØŒ Ù…Ù† Ø§Ù„Ù…ÙˆÙ‚Ø¹ Ø£Ùˆ Ù…Ù† ÙˆØ§ØªØ³Ø§Ø¨.",
    statOpen: "Ù…Ù†Ø§Ù‚ØµØ§Øª Ù…ÙØªÙˆØ­Ø©",
    statContractors: "Ù…Ù‚Ø§ÙˆÙ„ÙˆÙ† Ù…Ø¹ØªÙ…Ø¯ÙˆÙ†",
    statAwarded: "Ù…Ø´Ø§Ø±ÙŠØ¹ ØªÙ…Øª ØªØ±Ø³ÙŠØªÙ‡Ø§",
    featuresTitle: "Ù…Ø¨Ù†ÙŠ Ø¹Ù„Ù‰ Ø§Ù„Ø«Ù‚Ø©",
    feature1Title: "Ù…Ù‚Ø§ÙˆÙ„ÙˆÙ† Ù…Ø¹ØªÙ…Ø¯ÙˆÙ†",
    feature1Body: "ØªÙØ±Ø§Ø¬Ø¹ ÙˆØ«Ø§Ø¦Ù‚ ÙƒÙ„ Ù…Ù‚Ø§ÙˆÙ„ Ù‚Ø¨Ù„ Ø£Ù† ÙŠØªÙ…ÙƒÙ† Ù…Ù† ØªÙ‚Ø¯ÙŠÙ… Ø§Ù„Ø¹Ø±ÙˆØ¶.",
    feature2Title: "Ø¹Ø±ÙˆØ¶ Ù…ØºÙ„Ù‚Ø© Ø£Ùˆ Ù…ÙØªÙˆØ­Ø©",
    feature2Body: "ÙŠØ®ØªØ§Ø± Ø§Ù„Ù…Ø§Ù„Ùƒ Ù…Ø§ Ø¥Ø°Ø§ ÙƒØ§Ù† Ø§Ù„Ù…ØªÙ‚Ø¯Ù…ÙˆÙ† ÙŠØ±ÙˆÙ† Ø¹Ø±ÙˆØ¶ Ø¨Ø¹Ø¶Ù‡Ù….",
    feature3Title: "ÙŠØ¹Ù…Ù„ Ø¹Ù„Ù‰ ÙˆØ§ØªØ³Ø§Ø¨",
    feature3Body: "ÙŠÙ…ÙƒÙ† Ù„Ù„Ù…Ù„Ø§Ùƒ ÙˆØ§Ù„Ù…Ù‚Ø§ÙˆÙ„ÙŠÙ† Ø§Ù„Ù†Ø´Ø± ÙˆØ§Ù„ØªØµÙØ­ ÙˆØªÙ‚Ø¯ÙŠÙ… Ø§Ù„Ø¹Ø±ÙˆØ¶ Ù…Ù† Ù…Ø­Ø§Ø¯Ø«Ø© ÙˆØ§ØªØ³Ø§Ø¨.",
    howTitle: "ÙƒÙŠÙ ÙŠØ¹Ù…Ù„",
    step1: "Ø£Ù†Ø´Ø¦ Ø­Ø³Ø§Ø¨Ùƒ",
    step2: "Ø§Ù†Ø´Ø± Ù…Ù†Ø§Ù‚ØµØ© Ø£Ùˆ Ù‚Ø¯Ù‘Ù… Ø¹Ø±Ø¶Ù‹Ø§",
    step3: "Ø§Ù…Ù†Ø­ Ø§Ù„ØªØ±Ø³ÙŠØ© ÙˆØªØ§Ø¨Ø¹",
    whatsappTitle: "Ø§Ø³ØªØ®Ø¯Ù… U-Tender Ø¹Ù„Ù‰ ÙˆØ§ØªØ³Ø§Ø¨",
    whatsappBody: "Ø§Ù…Ø³Ø­ Ø§Ù„Ø±Ù…Ø² Ø¨ÙƒØ§Ù…ÙŠØ±Ø§ Ù‡Ø§ØªÙÙƒ. ØªÙØªØ­ Ø§Ù„Ù…Ø­Ø§Ø¯Ø«Ø© Ù…Ø¹ U-Tender. Ø£Ø±Ø³Ù„ ÙƒÙ„Ù…Ø© utender Ù„Ù„Ø¨Ø¯Ø¡.",
    qrAlt: "Ø±Ù…Ø² QR Ù„ÙØªØ­ U-Tender Ø¹Ù„Ù‰ ÙˆØ§ØªØ³Ø§Ø¨",
  },
  header: {
    logOut: "تسجيل الخروج",
    account: "الحساب",
  },
  language: {
    label: "اللغة",
    en: "English",
    ar: "العربية",
  },
  auth: {
    login: {
      heading: "تسجيل الدخول",
      email: "البريد الإلكتروني",
      password: "كلمة المرور",
      submit: "تسجيل الدخول",
      submitting: "جارٍ تسجيل الدخول…",
      noAccount: "ليس لديك حساب؟",
      signupLink: "إنشاء حساب",
      forgotPassword: "نسيت كلمة المرور؟",
      genericError: "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
    },
    signup: {
      heading: "إنشاء حساب",
      iAmA: "أنا...",
      propertyOwner: "مالك عقار",
      contractor: "مقاول",
      companyName: "اسم الشركة",
      companyNameHint: "ستقوم بتقديم مستندات التحقق بعد إنشاء الحساب.",
      fullName: "الاسم الكامل",
      email: "البريد الإلكتروني",
      password: "كلمة المرور",
      submit: "إنشاء الحساب",
      submitting: "جارٍ الإنشاء…",
      haveAccount: "لديك حساب بالفعل؟",
      loginLink: "تسجيل الدخول",
      genericError: "تعذر إنشاء الحساب.",
    },
    forgotPassword: {
      heading: "إعادة تعيين كلمة المرور",
      description: "أدخل البريد الإلكتروني لحسابك، وسنرسل لك رابطًا لإعادة تعيين كلمة المرور.",
      email: "البريد الإلكتروني",
      submit: "إرسال رابط إعادة التعيين",
      submitting: "جارٍ الإرسال…",
      sent: "إذا كان هناك حساب مرتبط بهذا البريد الإلكتروني، فسيتم إرسال رابط إعادة التعيين إليه.",
      backToLogin: "العودة إلى تسجيل الدخول",
    },
    resetPassword: {
      heading: "اختر كلمة مرور جديدة",
      newPassword: "كلمة المرور الجديدة",
      submit: "إعادة تعيين كلمة المرور",
      submitting: "جارٍ إعادة التعيين…",
      success: "تم إعادة تعيين كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول.",
      invalidToken: "رابط إعادة التعيين غير صالح أو منتهي الصلاحية.",
      goToLogin: "الذهاب إلى تسجيل الدخول",
      requestNew: "طلب رابط جديد لإعادة التعيين",
      missingToken: "لم يتم توفير رمز إعادة التعيين.",
    },
    verifyEmail: {
      heading: "جارٍ التحقق من بريدك الإلكتروني…",
      success: "تم التحقق من بريدك الإلكتروني بنجاح.",
      invalidToken: "رابط التحقق غير صالح أو منتهي الصلاحية.",
      continue: "متابعة",
      missingToken: "لم يتم توفير رمز التحقق.",
    },
    changePassword: {
      heading: "تغيير كلمة المرور",
      currentPassword: "كلمة المرور الحالية",
      newPassword: "كلمة المرور الجديدة",
      submit: "تغيير كلمة المرور",
      submitting: "جارٍ التغيير…",
      success: "تم تغيير كلمة المرور.",
    },
    emailVerifyBanner: {
      message: "يرجى تأكيد بريدك الإلكتروني.",
      resend: "إعادة إرسال رسالة التحقق",
      sent: "تم إرسال رسالة التحقق.",
    },
  },
  clarifications: {
    heading: "الأسئلة والأجوبة",
    noQuestions: "لا توجد أسئلة بعد.",
    sealedBidder: "مقاول مغفل الهوية",
    privateTag: "خاص",
    writeAnswerPlaceholder: "اكتب إجابة…",
    answerButton: "إجابة",
    awaitingAnswer: "بانتظار إجابة من المالك.",
    shareCheckboxLabel: "مشاركة هذا السؤال والجواب مع المقاولين الآخرين بعد الإجابة عليه",
    askPlaceholder: "اطرح سؤالاً على المالك حول هذا المشروع…",
    askButton: "إرسال السؤال",
    askError: "تعذر إرسال سؤالك.",
    answerError: "تعذر إرسال إجابتك.",
  },
  contractor: {
    roleLabel: "مقاول",
    dashboard: {
      kpiActiveBids: "العروض النشطة",
      kpiProjectsWon: "المشاريع الفائزة",
      kpiTotalBids: "إجمالي العروض المقدمة",
      myBids: "عروضي",
      browseOpenProjects: "تصفح المشاريع المفتوحة",
      noBidsYetPrefix: "لم تقدم أي عروض بعد.",
      banner: {
        documentsIncompleteTitle: "أكمل التحقق من شركتك",
        documentsIncompleteBody: "قم برفع مستنداتك ليتمكن أحد المسؤولين من مراجعة حسابك.",
        documentsIncompleteCta: "متابعة التحقق",
        submittedTitle: "الطلب قيد المراجعة",
        submittedBody: "يقوم أحد المسؤولين بمراجعة مستنداتك. سنُعلمك فور اتخاذ القرار.",
        submittedCta: "عرض الطلب المُقدَّم",
        changesRequestedTitle: "تم طلب تعديلات",
        changesRequestedBody: "يجب إعادة رفع مستند واحد أو أكثر قبل الموافقة على حسابك.",
        changesRequestedCta: "مراجعة وإعادة الرفع",
        paymentRequiredTitle: "اشترك لفتح إمكانية تقديم العروض",
        paymentRequiredBody: "تم التحقق من حسابك — اشترك لعرض المخططات وتقديم العروض.",
        paymentRequiredCta: "عرض الباقات",
        suspendedTitle: "الحساب موقوف",
        suspendedBody: "تم إيقاف حسابك من قبل مسؤول الموقع. تواصل مع الدعم إذا كنت تعتقد أن هذا خطأ.",
      },
    },
    feed: {
      eyebrow: "مقاول · المشاريع المفتوحة",
      heading: "مشاريع مفتوحة لتقديم العروض",
      sortedNewest: "مرتبة حسب الأحدث نشرًا.",
      sortedClosest: "مرتبة حسب الأقرب إغلاقًا.",
      subscribeBanner: "تمت الموافقة عليك، لكن المخططات والعروض تبقى مقفلة حتى تشترك.",
      viewPlans: "عرض الباقات",
      searchPlaceholder: "ابحث بالعنوان أو الموقع أو نطاق العمل…",
      allTrades: "كل التخصصات",
      sortClosest: "الأقرب إغلاقًا",
      sortNewest: "الأحدث أولاً",
      noMatch: "لا توجد مشاريع مطابقة لعوامل التصفية.",
      noOpenProjects: "لا توجد مشاريع مفتوحة حاليًا. تحقق مرة أخرى قريبًا.",
      deadline: "الموعد النهائي",
      offersSoFar: "العروض حتى الآن",
      trade: "التخصص",
      bidPlaced: "تم تقديم العرض",
      lockedTitle: "اشترك لعرض المخططات",
      lockedDescription: "افتح المخططات الكاملة وتفاصيل نطاق العمل والقدرة على تقديم العروض.",
    },
    status: {
      suspendedTitle: "الحساب موقوف",
      suspendedBody:
        "تم إيقاف حسابك من قبل مسؤول الموقع. لا يمكنك عرض مشاريع جديدة أو تقديم عروض أثناء الإيقاف. تواصل مع الدعم إذا كنت تعتقد أن هذا خطأ.",
      approvedTitle: "تمت الموافقة عليك",
      approvedBody: "توجه إلى لوحة التحكم لتصفح المشاريع المفتوحة.",
      eyebrow: "مقاول · التحقق من الحساب",
      heading: "حالة الطلب",
      changesRequestedTitle: "تم طلب تعديلات — يجب إعادة رفع مستند واحد أو أكثر",
      underReviewTitle: "الطلب قيد المراجعة",
      submittedOn: "تاريخ التقديم",
      pending: "قيد الانتظار",
      actionNeeded: "يتطلب إجراء",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      adminNote: "ملاحظة المسؤول:",
      reupload: "إعادة الرفع",
      upload: "رفع",
      footerNote:
        "سيتم إعلامك بمجرد الموافقة الكاملة على حسابك. يبقى الوصول الكامل إلى المخططات والعروض مقفلاً حتى ذلك الحين.",
    },
    verify: {
      eyebrow: "مقاول · التحقق من الحساب",
      heading: "تحقق من شركتك",
      description: "قدّم المستندات أدناه ليتمكن مسؤول الموقع من تفعيل حسابك.",
      companyName: "اسم الشركة",
      licenseNumber: "رقم الترخيص",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      submitting: "جارٍ الإرسال…",
      submit: "إرسال للمراجعة",
      uploadError: "تعذر رفع المستند.",
      submitError: "تعذر الإرسال للمراجعة.",
    },
    offer: {
      deadlineLabel: "الموعد النهائي",
      closed: "مغلق",
      scope: "نطاق العمل",
      drawings: "المخططات",
      downloadZip: "تنزيل الكل كملف .zip",
      noDrawings: "لم يتم رفع أي مخططات لهذا المشروع.",
      biddingClosedNotice: "أُغلق تقديم العروض على هذا المشروع.",
      yourFinalOffer: "عرضك النهائي:",
      awardedTo: "تم الترسية على",
      anotherContractor: "مقاول آخر",
      noAwardNotice: "قرر المالك عدم ترسية هذا المشروع.",
      bidAmount: "قيمة عرضك (دولار أمريكي)",
      timeline: "الجدول الزمني المتوقع",
      timelinePlaceholder: "مثال: 3 أسابيع من بدء العمل",
      messageToOwner: "رسالة إلى المالك",
      messagePlaceholder: "اشرح منهجك ومواد العمل وأي تفاصيل لا تغطيها المخططات.",
      updateOffer: "تحديث العرض",
      submitOffer: "تقديم العرض",
      withdraw: "سحب العرض",
      withdrawing: "جارٍ السحب…",
      tipsHeading: "نصائح للفوز بالعروض",
      tip1: "أشر إلى تفاصيل محددة من المخططات — فهذا يدل على أنك راجعتها بعناية.",
      tip2: "يمكن للمالكين رؤية تقييمك ومراجعاتك السابقة بجانب عرضك.",
      tip3: "يمكنك تعديل عرضك في أي وقت قبل الموعد النهائي.",
      withdrawError: "تعذر سحب العرض.",
      submitError: "تعذر تقديم العرض.",
      notAvailableNotice: "هذا المشروع غير متاح لك حاليًا.",
    },
  },
  owner: {
    roleLabel: "مالك",
    dashboard: {
      statusAll: "كل الحالات",
      statusDraft: "مسودة",
      statusOpen: "مفتوح",
      statusAwaitingReview: "بانتظار المراجعة",
      statusUnderEvaluation: "قيد التقييم",
      statusAwarded: "تمت الترسية",
      statusNoAward: "بلا ترسية",
      statusCanceled: "ملغى",
      statusExpired: "منتهي الصلاحية",
      eyebrow: "لوحة تحكم المالك",
      heading: "مشاريعك",
      newProject: "+ مشروع جديد",
      kpiOpen: "مفتوح",
      kpiAwaitingReview: "بانتظار المراجعة",
      kpiUnderEvaluation: "قيد التقييم",
      kpiAwarded: "تمت الترسية",
      kpiTotalOffers: "إجمالي العروض",
      emptyStatePrefix: "لم تنشر أي مشروع بعد.",
      emptyStateLink: "انشر أول مشروع لك",
      emptyStateSuffix: "لتبدأ باستقبال العروض.",
      searchPlaceholder: "ابحث بالعنوان أو الموقع…",
      allTenderTypes: "كل أنواع العطاءات",
      sealed: "مغلق (سري)",
      ownerVisible: "مرئي للمالك",
      noMatch: "لا توجد مشاريع مطابقة لعوامل التصفية.",
      nothingHere: "لا يوجد شيء هنا.",
      offersReceived: "عرض/عروض مستلمة",
      readyToReview: "جاهز للمراجعة",
      deadline: "الموعد النهائي",
      trade: "التخصص",
      posted: "تاريخ النشر",
    },
    projectNew: {
      eyebrow: "مشروع جديد",
      heading: "انشر مشروعًا",
      description: "أضف مخططاتك وحدّد موعدًا نهائيًا — لا يمكن للمقاولين تقديم عروض إلا قبل إغلاقه.",
      tenderType: "نوع العطاء",
      ownerVisibleToggle: "مرئي للمالك",
      sealedToggle: "مغلق (سري)",
      ownerVisibleHint: "يمكنك رؤية العروض فور ورودها. يُثبَّت النوع بمجرد وصول أول عرض.",
      sealedHint: "تبقى العروض مخفية عنك حتى يُغلق تقديم العروض. يُثبَّت النوع بمجرد وصول أول عرض.",
      title: "عنوان المشروع",
      titlePlaceholder: "مثال: دوبلكس شارع مابل — استبدال السقف",
      address: "عنوان الموقع",
      addressPlaceholder: "الشارع، المدينة، المنطقة",
      trade: "التخصص",
      tradePlaceholder: "مثال: أسقف، هياكل، أسوار",
      scope: "نطاق العمل",
      scopePlaceholder: "صف العمل المطلوب. سيستخدم المقاولون هذا الوصف مع مخططاتك لتسعير عروضهم.",
      drawings: "المخططات",
      drawingsHint: "PDF أو DWG أو JPG أو PNG أو ملف .zip للمخططات — حتى 50 ميغابايت إجمالاً",
      drawingsAccessNote: "فقط المقاولون المعتمدون والمشتركون يمكنهم عرض هذه الملفات.",
      deadline: "الموعد النهائي لتقديم العروض",
      deadlineNote: "لا تُقبل العروض بعد هذا الوقت.",
      postProject: "نشر المشروع",
      posting: "جارٍ النشر…",
      saveAsDraft: "حفظ كمسودة",
      draftNote: "المسودة مرئية لك فقط. يمكنك نشرها لاحقًا من صفحة المشروع عندما تكون جاهزًا لاستقبال العروض.",
      sidebarHeading: "قبل أن تنشر",
      tip1: "المخططات الواضحة تُنتج عروضًا أدق — أضف الأبعاد قدر الإمكان.",
      tip2: "امنح المقاولين 5 إلى 7 أيام على الأقل لتسعير العمل بشكل صحيح.",
      tip3: "لن يتم تحصيل أي رسوم منك. نشر المشاريع ومراجعة العروض مجاني لملاك العقارات.",
      validationError: "العنوان والموقع والموعد النهائي حقول مطلوبة.",
      submitError: "تعذر إنشاء المشروع.",
    },
    projectDetail: {
      reviewOffers: "مراجعة العروض",
      sealedBadge: "مغلق (سري)",
      ownerVisibleBadge: "مرئي للمالك",
      publish: "نشر — بدء استقبال العروض",
      closeEarly: "إغلاق تقديم العروض مبكرًا",
      startEvaluation: "بدء التقييم",
      markNoAward: "وضع علامة بلا ترسية",
      cancelProject: "إلغاء المشروع",
      noDrawings: "لم يتم رفع أي مخططات بعد",
      downloadZip: "تنزيل الكل كملف .zip",
      hideHistory: "إخفاء سجل المراجعات",
      viewHistory: "عرض سجل المراجعات",
      noHistory: "لا يوجد سجل مراجعات بعد.",
      current: "(الحالي)",
      view: "عرض",
      addDrawings: "إضافة مخططات",
      zipHint: "يمكنك أيضًا رفع ملف .zip يحتوي على المخططات.",
      scope: "نطاق العمل",
      lowestBid: "أقل عرض",
      averageBid: "متوسط العروض",
      highestBid: "أعلى عرض",
      sealedBidsReceived: "عرض/عروض سرية مستلمة",
      sealedExplanation:
        "هذا عطاء مغلق (سري) — تبقى هويات المقاولين وقيم عروضهم مخفية عنك حتى يُغلق تقديم العروض. أغلق تقديم العروض لكشفها وتقييمها.",
      noOffersYet: "لا توجد عروض بعد. يمكن للمقاولين تقديم عروض حتى الموعد النهائي أعلاه.",
      contractorCol: "المقاول",
      ratingCol: "التقييم",
      bidCol: "العرض",
      timelineCol: "الجدول الزمني",
      revisedSuffix: "مُعدَّل ×",
      approve: "قبول",
      closeToAwardHint: "أغلق تقديم العروض للترسية",
      contractorReply: "رد المقاول",
      noReply: "لا توجد رسالة رد.",
      revisionHistory: "سجل المراجعات",
      rateContractor: "قيّم",
      theContractor: "المقاول",
      submittedOn: "تاريخ التقديم",
      ratingPlaceholder: "كيف سار العمل؟ اختياري، لكنه يساعد الملاك الآخرين.",
      submitReview: "إرسال التقييم",
      approveError: "تعذر قبول هذا العرض.",
      drawingsError: "تعذر إضافة المخططات.",
      reviewError: "تعذر إرسال التقييم.",
      statusError: "تعذر تحديث حالة هذا المشروع.",
    },
    verify: {
      eyebrow: "مالك · التحقق من الحساب",
      heading: "تحقق من حسابك",
      description: "قدّم المستندات أدناه ليتمكن مسؤول الموقع من تفعيل حسابك.",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      submitting: "جارٍ الإرسال…",
      submit: "إرسال للمراجعة",
      uploadError: "تعذر رفع المستند.",
      submitError: "تعذر الإرسال للمراجعة.",
    },
    status: {
      suspendedTitle: "الحساب موقوف",
      suspendedBody:
        "تم إيقاف حسابك من قبل مسؤول الموقع. لا يمكنك نشر أو إدارة المشاريع أثناء الإيقاف. تواصل مع الدعم إذا كنت تعتقد أن هذا خطأ.",
      approvedTitle: "تمت الموافقة عليك",
      approvedBody: "توجه إلى لوحة التحكم لنشر مشروع.",
      eyebrow: "مالك · التحقق من الحساب",
      heading: "حالة الطلب",
      changesRequestedTitle: "تم طلب تعديلات — يجب إعادة رفع مستند واحد أو أكثر",
      underReviewTitle: "الطلب قيد المراجعة",
      submittedOn: "تاريخ التقديم",
      pending: "قيد الانتظار",
      actionNeeded: "يتطلب إجراء",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      adminNote: "ملاحظة المسؤول:",
      reupload: "إعادة الرفع",
      upload: "رفع",
      footerNote:
        "سيتم إعلامك بمجرد الموافقة الكاملة على حسابك. يبقى نشر المشاريع وإدارتها مقفلاً حتى ذلك الحين.",
    },
  },
  admin: {
    nav: {
      requirements: "متطلبات المستندات",
      review: "مراجعة الطلبات",
      contractors: "جميع المقاولين",
      owners: "جميع الملاك",
      offers: "جميع العروض",
      projects: "جميع المشاريع",
      cms: "محتوى الموقع",
    },
    owners: {
      eyebrow: "المسؤول · الملاك",
      heading: "جميع ملاك العقارات",
      total: "الإجمالي",
      empty: "لم يسجل أي مالك بعد.",
      name: "الاسم",
      status: "الحالة",
      projects: "المشاريع",
      manage: "إدارة",
    },
    ownerDetail: {
      docReviewError: "تعذر تحديث هذا المستند.",
      approveError: "تعذر قبول هذا المالك.",
      rejectError: "تعذر طلب التعديلات.",
      suspendError: "تعذر تحديث صلاحية الوصول للحساب.",
      deleteError: "تعذر حذف هذا المالك.",
      suspended: "موقوف",
      documentsHeading: "مستندات التحقق",
      document: "المستند",
      statusCol: "الحالة",
      approve: "قبول",
      reject: "رفض",
      applicationHeading: "الطلب",
      currentStatus: "الحالة الحالية",
      approveApplication: "الموافقة على المالك",
      requestChanges: "طلب تعديلات",
      accessHeading: "الوصول إلى الحساب",
      reactivate: "إعادة تفعيل الحساب",
      suspend: "إيقاف الحساب",
      suspendedNote: "لا يمكن لهذا المالك نشر أو إدارة المشاريع حتى تتم إعادة التفعيل.",
      suspendNote: "يمنع المالك فورًا من نشر أو إدارة المشاريع، دون حذف أي شيء.",
      dangerZone: "منطقة الخطر",
      deleteBlockedNote:
        "قام هذا المالك بنشر مشاريع. أوقف الحساب بدلاً من حذفه، للحفاظ على سجل المشاريع والعروض سليماً للمقاولين المعنيين.",
      deleteNote: "لا يملك هذا المالك أي مشاريع بعد، لذا فإن الحذف يزيل الحساب بالكامل. لا يمكن التراجع عن هذا.",
      deleteConfirm: "هل تريد حذف حساب هذا المالك نهائيًا؟ لا يمكن التراجع عن هذا.",
      deleteAccount: "حذف الحساب",
      projectsHeading: "المشاريع المنشورة",
      noProjects: "لم ينشر هذا المالك أي مشاريع بعد.",
      projectTitleCol: "المشروع",
      projectStatusCol: "الحالة",
      projectOffersCol: "العروض",
      viewProject: "عرض",
    },
    offers: {
      eyebrow: "المسؤول · العروض",
      heading: "جميع العروض",
      total: "الإجمالي",
      empty: "لم يتم تقديم أي عروض بعد.",
      project: "المشروع",
      contractor: "المقاول",
      amount: "القيمة",
      status: "الحالة",
      tenderType: "نوع العطاء",
      submitted: "تاريخ التقديم",
      revised: "مُعدَّل",
      suspendedBadge: "العرض موقوف",
      viewProject: "عرض المشروع كاملاً",
    },
    projects: {
      eyebrow: "المسؤول · المشاريع",
      heading: "جميع المشاريع",
      total: "الإجمالي",
      empty: "لم يُنشر أي مشروع بعد.",
      owner: "المالك",
      title: "المشروع",
      status: "الحالة",
      offers: "العروض",
      suspendedBadge: "موقوف",
      manage: "إدارة",
    },
    projectDetail: {
      eyebrow: "المسؤول · المشاريع",
      suspended: "موقوف",
      editHeading: "تفاصيل المشروع",
      titleLabel: "العنوان",
      addressLabel: "العنوان الجغرافي",
      descriptionLabel: "نطاق العمل",
      tradeLabel: "التخصص",
      deadlineLabel: "الموعد النهائي للعروض",
      saveChanges: "حفظ التغييرات",
      saveError: "تعذر حفظ التغييرات.",
      accessHeading: "الظهور في السوق",
      reactivate: "إعادة تفعيل المشروع",
      suspend: "إيقاف المشروع",
      suspendedNote: "هذا المشروع مخفي عن قائمة المقاولين ولا يمكنه استقبال عروض جديدة حتى تتم إعادة التفعيل.",
      suspendNote: "يخفي هذا المشروع فورًا عن قائمة المقاولين ويمنع العروض الجديدة، دون حذف أي شيء.",
      suspendError: "تعذر تحديث ظهور المشروع.",
      dangerZone: "منطقة الخطر",
      deleteBlockedNote:
        "يحتوي هذا المشروع على عروض. أوقفه بدلاً من حذفه، للحفاظ على سجل العروض سليماً للمقاولين المعنيين.",
      deleteNote: "لا يحتوي هذا المشروع على أي عروض بعد، لذا فإن الحذف يزيله بالكامل. لا يمكن التراجع عن هذا.",
      deleteConfirm: "هل تريد حذف هذا المشروع نهائيًا؟ لا يمكن التراجع عن هذا.",
      deleteProject: "حذف المشروع",
      deleteError: "تعذر حذف هذا المشروع.",
      offersHeading: "العروض على هذا المشروع",
      noOffers: "لم يتم تقديم أي عروض على هذا المشروع.",
      contractorCol: "المقاول",
      amountCol: "القيمة",
      timelineCol: "الجدول الزمني",
      statusCol: "الحالة",
      actionsCol: "",
      edit: "تعديل",
      editOfferHeading: "تعديل العرض",
      amountFieldLabel: "القيمة (بالدولار)",
      timelineFieldLabel: "الجدول الزمني",
      messageFieldLabel: "الرسالة",
      saveOffer: "حفظ",
      cancel: "إلغاء",
      editOfferError: "تعذر حفظ هذا العرض.",
      suspendOffer: "إيقاف",
      reactivateOffer: "إعادة تفعيل",
      suspendOfferError: "تعذر تحديث هذا العرض.",
      deleteOffer: "حذف",
      deleteOfferError: "تعذر حذف هذا العرض.",
      deleteOfferConfirm: "هل تريد حذف هذا العرض نهائيًا؟ لا يمكن التراجع عن هذا.",
      deleteOfferBlocked: "تمت ترسية هذا العرض — أوقفه بدلاً من حذفه.",
      offerSuspendedBadge: "العرض موقوف",
    },
    requirements: {
      eyebrow: "المسؤول · متطلبات المستندات",
      heading: "المستندات المطلوبة",
      description:
        "فعّل أو عطّل المتطلبات، أو أزل أحدها نهائيًا. تُطبَّق التغييرات على الطلبات الجديدة فورًا — الحسابات التي تمت الموافقة عليها سابقًا لا تتأثر.",
      forContractors: "للمقاولين",
      forOwners: "للملاك",
      emptyForScope: "لا توجد متطلبات مُعدة لهذه المجموعة بعد.",
      toggleRequiredFor: "تبديل حالة الإلزام لـ",
      required: "مطلوب",
      optional: "اختياري",
      removeTitle: "إزالة المتطلب",
      namePlaceholder: "اسم المستند، مثال: الهوية المدنية",
      descriptionPlaceholder: "وصف مختصر يظهر لمقدم الطلب",
      addForOwners: "+ إضافة متطلب للملاك",
      addForContractors: "+ إضافة متطلب للمقاولين",
      addError: "تعذر إضافة المتطلب.",
      updateError: "تعذر تحديث المتطلب.",
      removeError: "تعذر إزالة المتطلب.",
    },
  },
};
