export type NavGroupKey =
  | 'finance' | 'tax' | 'assets' | 'procurement' | 'sales'
  | 'production' | 'operations' | 'people' | 'governance' | 'system';

import type { ComponentType } from 'react';

export type Lang = 'ar' | 'en';
export type CompanyScope = 'holding' | 'gym' | 'restaurant' | 'manufacturing';
export type View =
  | 'executive' | 'core' | 'finance' | 'aging' | 'returns' | 'salesReturns' | 'purchaseReturns' | 'openingBalances' | 'vatReturn' | 'withholdingTax' | 'exciseTax' | 'zakatIncomeTax' | 'budget' | 'transactions' | 'inventory' | 'inventoryTraceability' | 'operationalControls'
  | 'sales' | 'purchases' | 'maintenance' | 'fleet' | 'legal' | 'users' | 'items' | 'dataReset' | 'chartOfAccounts' | 'manualJournals' | 'cipProjects' | 'reports' | 'crm' | 'treasury' | 'leases' | 'assets' | 'prepaids' | 'accruals'
  | 'gym' | 'restaurant' | 'manufacturing' | 'quality' | 'foodSafety' | 'hr'
  | 'workbench' | 'finalCompletion' | 'close' | 'assurance' | 'compliance' | 'security' | 'accessGovernance' | 'fx' | 'audit' | 'it';

export type NavItem = {
  key: View;
  ar: string;
  en: string;
  icon: ComponentType<{size?: number}>;
  scope: CompanyScope[];
  // AUDIT H-06: permission prefixes that grant access to this section.
  // A user needs at least one of them; sections without it stay visible.
  requires?: string[];
  // Sidebar grouping. Items without a group sit at the top, ungrouped.
  group?: NavGroupKey;
};
