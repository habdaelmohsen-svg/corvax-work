import type { View } from './types';

/*
 * One auditable registry for every drill-through exposed by the executive
 * home page. Keeping the destinations out of JSX prevents labels and routes
 * from drifting apart as the dashboard evolves.
 */
export const EXECUTIVE_NAVIGATION_TARGETS = {
  revenue: 'finance',
  netProfit: 'finance',
  totalAssets: 'assets',
  cashBalance: 'treasury',
  gymMembers: 'gym',
  grossProfit: 'finance',
  restaurantSales: 'restaurant',
  foodCost: 'restaurant',
  restaurantOrders: 'restaurant',
  financialPerformance: 'finance',
  expenseBreakdown: 'finance',
  allAlerts: 'workbench',
  lowStockAlert: 'inventory',
  overdueInvoiceAlert: 'aging',
  purchaseApprovalAlert: 'purchases',
  leaveApprovalAlert: 'hr',
  assuranceAlert: 'assurance',
  receivables: 'aging',
  payables: 'aging',
  cashFlow: 'treasury',
  journalEntry: 'manualJournals',
  salesInvoice: 'sales',
  purchaseOrder: 'purchases',
  payment: 'treasury',
  closePeriod: 'close',
  profitReport: 'finance',
  trialBalance: 'finance',
  reportsCenter: 'reports',
  dataQuality: 'assurance',
  compliance: 'compliance',
  openRisks: 'audit',
  auditFindings: 'audit',
  governance: 'audit',
} as const satisfies Record<string, View>;

export type ExecutiveNavigationKey = keyof typeof EXECUTIVE_NAVIGATION_TARGETS;

export function navigateFromExecutive(
  key: ExecutiveNavigationKey,
  onNavigate: (view: View) => void,
): View {
  const target = EXECUTIVE_NAVIGATION_TARGETS[key];
  onNavigate(target);
  return target;
}
