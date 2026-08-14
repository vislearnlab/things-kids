// IRB-approved adult consent form, study #811123.
//
// REPRODUCED VERBATIM. Do not reword, condense, or "tidy" this text — it is
// the approved instrument, and any edit needs to go through the IRB first.
// Kept in its own module so it can be diffed against the approved document
// without wading through experiment code.
//
// Shown only when PROLIFIC_PID is present in the URL. The museum kiosk keeps
// its own parental consent screen in experiment.ts.

export const CONSENT_STUDY_TITLE = 'Language & visual category learning across development';
export const CONSENT_STUDY_NUMBER = '811123';

type Section = { heading: string; body: string[]; bullets?: string[]; after?: string[] };

export const CONSENT_SECTIONS: Section[] = [
  {
    heading: 'Study Title and Number',
    body: [
      `Title: ${CONSENT_STUDY_TITLE}`,
      `Study #${CONSENT_STUDY_NUMBER}`,
    ],
  },
  {
    heading: 'Principal Investigator',
    body: ['Bria Long, Ph.D., Department of Psychology, University of California, San Diego'],
  },
  {
    heading: 'Principal Investigator, Research Team, and Emergency Contact',
    body: [
      'The Principal Investigator can be reached at 650-644-7235 and the research team can be reached at vislearnlab@ucsd.edu. Please use the same phone number or email in case of emergencies.',
    ],
  },
  {
    heading: 'Study Sponsor',
    body: [
      'The National Institute of Child Health and Human Development, the study sponsor, is paying UC San Diego to conduct this research study.',
    ],
  },
  {
    heading: 'Study Overview',
    body: [
      'This research study is being conducted to better understand the development of language and category representations.',
      'This form explains the research so that you may make an informed decision about participation for you:.',
    ],
    bullets: [
      'Research is voluntary - whether or not you participate is your decision. You can discuss your decision with others (such as family or friends).',
      'You can say yes, but change your mind later. If you say no, we will not hold your decision against you.',
      'Please ask the study team questions about anything that is not clear, and feel free to ask questions and mention concerns before, during, and after the research.',
      'You may consult with friends, family, or anyone else before deciding whether or not to participate in the study.',
      'You may download a copy of this consent form to keep.',
    ],
    after: [
      'The purpose of this research study is to understand the relationship between language learning and everyday learning experiences. We will investigate how both children and adults represent language and the visual categories in the world around us, and interpret different categories and objects across age.',
      'If you take part in this research, you will answer survey questions or play a few games or activities for between 5 and 60 minutes.',
      'Risks associated with participation in this study are minimal. You may feel boredom while answering questions or playing any games or activities. There is also a risk of loss of confidentiality that is minimal since all data provided by Prolific is anonymous. A complete listing of possible risks and discomforts associated with this study can be found in Section 8 of this document.',
      'We cannot promise any benefit to you or to others from you participating in this research. However, possible benefits include enjoyment from engaging in the study because of the stimulating nature of the experimental games. You may also benefit from the satisfaction of having contributed to research on development in early childhood. There are also potential benefits to educational and public policy regarding the benefits of supporting language development in diverse populations and in children who struggle with early category learning.',
      'The alternative to being in this study is not to participate.',
      'More detailed information about this research study is provided below.',
    ],
  },
  {
    heading: 'Whom can I talk to if I have questions?',
    body: [
      'If during your participation in the study you have questions or concerns, or if you think the research has hurt you, contact the research team with the information listed in Section 3 on the first page of this form. You should not agree to participate in this study until the research team has answered any questions you have about the study, including information contained in this form.',
      'If before or during your participation in the study you have questions about your rights as a research participant, or you want to talk to someone outside the research team, please contact:',
      'UC San Diego Office of IRB Administration at 858-246-4777 or irb@ucsd.edu',
    ],
  },
  {
    heading: 'How many people will take part?',
    body: ['We plan to study around 1000 adults in these studies online using Prolific.'],
  },
  {
    heading: 'What happens if I take part in the research?',
    body: [
      'As you read this form, ask questions if something is not clear. You may be asked to answer survey questions or play a few games or activities that will take between 5-60 minutes as specified in the study description. Survey questions, for example, if you are a parent, may include questions about the kinds of things (e.g., books, toys) present in your child’s home environment. An example game you would play would be to click on an image on the screen that matches a word you hear being said out loud or typing out labels for objects you see on the screen. We will record the images/words that are shown to you on the screen and information about your responses. You may discontinue your participation at any time.',
    ],
  },
  {
    heading: 'What are the risks and possible discomforts?',
    body: [
      'Participation in this study involves minimal risks or discomforts. There is minimal risk of boredom with the task.',
      'Risks of Loss of Confidential Information: There is also a risk that information about you could be released to an unauthorized party. To minimize this risk, study information will be labeled with a subject code instead of your Prolific ID or other information that can easily identify you, which will be kept separate from the rest of the study information.',
    ],
  },
  {
    heading: 'How will information about me be protected?',
    body: [
      'We will not be asking for personally identifying information and while we cannot guarantee complete confidentiality, we will limit access to information about you. Only people who have a need to review your personal information (e.g. Prolific ID) have access. These people might include:',
    ],
    bullets: [
      'Members of the research team and other staff or representatives of UCSD whose work is related to the research or to protecting your rights and safety.',
      'Representatives of the study sponsor.',
      'Representatives of Federal and other regulatory agencies who make sure the study is done properly and that your rights and safety are protected.',
    ],
    after: [
      'Study information will be labeled with a subject code instead of your Prolific ID or other identifiable information. The record linking the subject code with your Prolific ID and other identifiable and demographic information, such as age and country of residence, will be kept separate from the rest of the study information.',
      'This research is covered by a Certificate of Confidentiality (CoC) from the National Institutes of Health. The researchers with this CoC may not disclose or use information, documents, or recordings that may identify you in any federal, state, or local civil, criminal, administrative, legislative, or other action, suit, or proceeding. For example, the information collected in this research cannot be used as evidence in a proceeding unless you consent to this use. Information, documents, or biospecimens protected by this CoC cannot be disclosed to anyone else who is not connected with the research, except:',
    ],
  },
  {
    heading: '',
    body: [],
    bullets: [
      'To a federal agency sponsoring this research when information is needed for auditing or program evaluations',
      'To meet the requirements of the U.S. FDA',
      'If a federal, state or local law requires disclosure such as a requirement to report a communicable disease',
      'If information about you must be disclosed to prevent serious harm to yourself or others such as child abuse, elder abuse or spousal abuse',
      'If you consent to the disclosure, including for your medical treatment, to an insurer or employer to obtain information about you',
      'If it is used for other scientific research, as allowed by federal regulations protecting research subjects.',
    ],
    after: [
      'This CoC also does not prevent you or a family member from voluntarily releasing information about yourself and your involvement in this research.',
    ],
  },
  {
    heading: 'Will I need to pay to participate in the research?',
    body: ['There will be no cost to you for participating in this study.'],
  },
  {
    heading: 'What if I agree to participate, but change my mind later?',
    body: [
      'You can stop participating at any time for any reason, and it will not be held against you or risk loss of compensation. If you stop participating, we may not be able to remove the information we have already collected about you because it is not linked to your identity.',
    ],
  },
  {
    heading: 'What will happen to information collected from me?',
    body: [
      'Data we collect with your identifiable information (e.g. your Prolific ID) as a part of this study will be de-identified before answering any research questions. Only this de-identified data will be shared with other investigators for other research purposes; we will remove your Prolific ID before use or sharing. Once identifiers have been removed, we will not ask for your consent for the use or sharing of your data in other research. In addition, data that have been de-identified will be uploaded to the Open Science Framework (OSF) for other researchers to access and use.',
      'While your privacy and confidentiality are very important to us and we will use safety measures to protect it, we cannot guarantee that your identity will never become known.',
    ],
  },
  {
    heading: 'Will I be compensated for participating in the research?',
    body: [
      'If you agree to take part in this research on Prolific, you will receive compensation directly through Prolific at a minimum rate of $12 an hour. There is no set compensation for your participation in this study and the total payment amount is dependent on the length of the study. If you agree to participate in this research through SONA, we will compensate you through SONA credit, following the standard rate at UCSD depending on the length of the study.',
    ],
  },
];

export const CONSENT_AGREEMENT_LINE =
  'I agree to participate in the research described in this form.';

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** The full form as HTML, for the on-screen scroll box. */
export function consentHTML(): string {
  let n = 0;
  return CONSENT_SECTIONS.map((s) => {
    const parts: string[] = [];
    if (s.heading) {
      n += 1;
      parts.push(`<h3>${n}. ${esc(s.heading)}</h3>`);
    }
    s.body.forEach((p) => parts.push(`<p>${esc(p)}</p>`));
    if (s.bullets?.length) {
      parts.push('<ul>' + s.bullets.map((b) => `<li>${esc(b)}</li>`).join('') + '</ul>');
    }
    s.after?.forEach((p) => parts.push(`<p>${esc(p)}</p>`));
    return parts.join('\n');
  }).join('\n');
}

/** Plain-text copy, so "You may download a copy of this consent form to keep"
 *  is something the participant can actually do. */
export function consentPlainText(): string {
  const out: string[] = [`${CONSENT_STUDY_TITLE}`, `Study #${CONSENT_STUDY_NUMBER}`, ''];
  let n = 0;
  CONSENT_SECTIONS.forEach((s) => {
    if (s.heading) {
      n += 1;
      out.push('', `${n}. ${s.heading}`, '');
    }
    s.body.forEach((p) => out.push(p, ''));
    s.bullets?.forEach((b) => out.push(`  - ${b}`));
    if (s.bullets?.length) out.push('');
    s.after?.forEach((p) => out.push(p, ''));
  });
  out.push('', CONSENT_AGREEMENT_LINE, '');
  return out.join('\n');
}
