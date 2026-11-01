export type DemoInboxMessage = {
  id: string
  sender: string
  subject: string
  category: string
  receivedAt: string
  body: string
  summary: string
  reply: string
}

export const demoInboxMessages: DemoInboxMessage[] = [
  {
    id: 'demo-message-1',
    sender: 'Amira Belhadj · synthetic example',
    subject: 'Interview time on 3 November',
    category: 'Interview coordination',
    receivedAt: '2026-10-31T16:20:00Z',
    body: 'Thank you for the invitation. Could we confirm the 10:00 slot on 3 November and the format of the technical interview?',
    summary: 'The sender asks to confirm the proposed interview time and learn what the technical interview will include.',
    reply: 'Hello Amira,\n\nThank you for your message. We will confirm the interview details shortly.\n\nBest regards,\nThe Vouch demo team',
  },
  {
    id: 'demo-message-2',
    sender: 'Lucas Moreau · synthetic example',
    subject: 'Question about dashboard tools',
    category: 'Candidate questions',
    receivedAt: '2026-10-30T09:05:00Z',
    body: 'Which business intelligence tools does the team use? I have mostly used matplotlib and would like to prepare.',
    summary: 'The sender asks which business intelligence tools are used by the team.',
    reply: 'Hello Lucas,\n\nThank you for asking. The hiring team can discuss the tools used for this role during the next conversation.\n\nBest regards,\nThe Vouch demo team',
  },
  {
    id: 'demo-message-3',
    sender: 'Daniel Okafor · synthetic example',
    subject: 'Availability next week',
    category: 'Interview coordination',
    receivedAt: '2026-10-29T18:40:00Z',
    body: 'I am available Tuesday to Thursday afternoons next week.',
    summary: 'The sender shares availability for an interview next week.',
    reply: 'Hello Daniel,\n\nThank you for sharing your availability. We will follow up with a proposed time.\n\nBest regards,\nThe Vouch demo team',
  },
]
