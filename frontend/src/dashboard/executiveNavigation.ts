import type { View } from './types';

/*
 * One auditable registry for every drill-through exposed by the executive
 * home page. Keeping the destinations out of JSX prevents labels and routes
 * from drifting apart as the dashboard evolves.
 */
export const EXECUTIVE_NAVIGATION_TARGETS = {
  // `finance` and `aging` are legacy route aliases, not entries in the
  // permission-filtered navigation registry. Sending KPI clicks to either
  // alias made Shell reject the navigation even for wildcard users. All
  // financial drill-throughs now land on the authorised reports centre.
  revenue: 'reports',
  netProfit: 'reports',
  totalAssets: 'assets',
  cashBalance: 'treasury',
  gymMembers: 'gym',
  grossProfit: 'reports',
  restaurantSales: 'restaurant',
  foodCost: 'restaurant',
  restaurantOrders: 'restaurant',
  financialPerformance: 'reports',
  expenseBreakdown: 'reports',
  allAlerts: 'workbench',
  lowStockAlert: 'inventory',
  overdueInvoiceAlert: 'reports',
  purchaseApprovalAlert: 'purchases',
  leaveApprovalAlert: 'hr',
  assuranceAlert: 'assurance',
  receivables: 'reports',
  payables: 'reports',
  cashFlow: 'treasury',
  journalEntry: 'manualJournals',
  salesInvoice: 'sales',
  purchaseOrder: 'purchases',
  payment: 'treasury',
  closePeriod: 'close',
  profitReport: 'reports',
  trialBalance: 'reports',
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
