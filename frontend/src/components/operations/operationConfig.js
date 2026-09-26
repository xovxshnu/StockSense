import { receiptApi, deliveryApi, transferApi, adjustmentApi } from '../../services/operationsApi';

// Display labels for backend status values. Presentation only: statuses come from
// the backend, and this is the single mapping used for badges and filter options.
export const STATUS_META = {
  DRAFT: { label: 'Draft', tone: 'neutral' },
  WAITING: { label: 'Waiting', tone: 'warning' },
  READY: { label: 'Ready', tone: 'info' },
  DONE: { label: 'Done', tone: 'success' },
  CANCELED: { label: 'Canceled', tone: 'danger' },
};

// `editableStatuses`: backend statuses in which the form may be edited (all others are read-only).
// Which backend action buttons to offer per backend status. This is a UI affordance
// only: the frontend never transitions state itself, the backend remains the authority
// and rejects invalid transitions. DONE and CANCELED intentionally have no actions.
//
// An action listed in `unverified` has an UNSPECIFIED resulting status in the contract.
// It is offered because it is the only endpoint that could apply, and the UI marks it so.
export const OPERATIONS = {
  receipts: {
    key: 'receipts',
    singular: 'Receipt',
    plural: 'Receipts',
    path: '/operations/receipts',
    api: receiptApi,
    statuses: ['DRAFT', 'READY', 'DONE', 'CANCELED'],
    editableStatuses: ['DRAFT'],
    actionsByStatus: {
      DRAFT: ['todo', 'cancel'],
      READY: ['validate', 'cancel'],
    },
  },
  deliveries: {
    key: 'deliveries',
    singular: 'Delivery',
    plural: 'Deliveries',
    path: '/operations/deliveries',
    api: deliveryApi,
    statuses: ['DRAFT', 'WAITING', 'READY', 'DONE', 'CANCELED'],
    editableStatuses: ['DRAFT'],
    // WAITING is passive: the backend decides when it becomes READY. The UI never
    // checks availability and never converts WAITING -> READY.
    // Shown as-is under the header; wording follows the blueprint definition of WAITING.
    statusNotes: {
      WAITING: 'Waiting: the backend has determined the requested stock is not available. This page shows the status the backend reports.',
    },
    actionsByStatus: {
      DRAFT: ['todo', 'cancel'],
      WAITING: ['cancel'],
      READY: ['validate', 'cancel'],
    },
  },
  transfers: {
    key: 'transfers',
    singular: 'Transfer',
    plural: 'Transfers',
    path: '/operations/transfers',
    api: transferApi,
    statuses: ['DRAFT', 'READY', 'DONE', 'CANCELED'],
    editableStatuses: ['DRAFT'],
    // UNRESOLVED CONTRACT: the state machine is DRAFT -> READY -> DONE but only
    // /validate exists (no /todo). It is not known whether validate on DRAFT moves to
    // READY or straight to DONE (which would execute the transfer). The frontend does not
    // guess: Validate on DRAFT is listed in `unverified`, so it asks for confirmation that
    // says so, and the UI then renders whatever status the backend returns.
    // No To Do action exists, and none is invented.
    statusNotes: {
      DRAFT: 'Validating a draft transfer is handled entirely by the backend. This page does not assume whether it becomes Ready or Done; it shows the status the backend reports.',
    },
    actionsByStatus: {
      DRAFT: ['validate', 'cancel'],
      READY: ['validate', 'cancel'],
    },
    unverified: { DRAFT: ['validate'], READY: [] },
  },
  adjustments: {
    key: 'adjustments',
    singular: 'Adjustment',
    plural: 'Adjustments',
    path: '/operations/adjustments',
    api: adjustmentApi,
    statuses: ['DRAFT', 'DONE'],
    editableStatuses: ['DRAFT'],
    actionsByStatus: {
      DRAFT: ['validate'],
    },
  },
};

export const ACTION_META = {
  todo: { label: 'Mark as To Do', busyLabel: 'Marking…', variant: 'primary' },
  validate: { label: 'Validate', busyLabel: 'Validating…', variant: 'primary' },
  cancel: {
    label: 'Cancel',
    busyLabel: 'Canceling…',
    variant: 'danger',
    confirm: {
      title: 'Cancel this operation?',
      message: 'The backend will cancel this operation. This cannot be undone.',
      confirmLabel: 'Cancel operation',
    },
  },
};

// Confirmation for an action whose effect on status the contract does not define.
export const UNVERIFIED_CONFIRM = {
  validate: {
    title: 'Validate this draft?',
    message: 'This asks the backend to validate the transfer. What happens next (for example whether it only becomes Ready or is completed) is decided by the backend and may not be reversible.',
    confirmLabel: 'Validate',
    confirmVariant: 'primary',
  },
};

// The confirmation an action needs, if any: destructive ones always; unverified ones too.
export function confirmFor(config, status, action) {
  if (ACTION_META[action].confirm) return ACTION_META[action].confirm;
  if (isUnverifiedAction(config, status, action)) return UNVERIFIED_CONFIRM[action] || null;
  return null;
}

export const UNVERIFIED_ACTION_HINT =
  'The resulting status is decided by the backend; the transition for this action is not yet specified.';

export function isUnverifiedAction(config, status, action) {
  return Boolean(config.unverified?.[status]?.includes(action));
}
