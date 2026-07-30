import {lazy, Suspense} from 'react';
import type {ReactNode} from 'react';
import type {CompanyScope, View} from './types';

const FinalCompletionPage = lazy(() => import('./finalCompletionPage').then((module) => ({default: module.FinalCompletionPage})));
const WorkspacePage = lazy(() => import('./workspacePage').then((module) => ({default: module.WorkspacePage})));
const ExecutivePage = lazy(() => import('./executive').then((module) => ({default: module.ExecutivePage})));
const CorePage = lazy(() => import('./financePages').then((module) => ({default: module.CorePage})));
const FinancePage = lazy(() => import('./financePages').then((module) => ({default: module.FinancePage})));
const AgingPage = lazy(() => import('./financePages').then((module) => ({default: module.AgingPage})));
const CreditNotesPage = lazy(() => import('./creditNotesPage').then((module) => ({default: module.CreditNotesPage})));
const WithholdingTaxPage = lazy(() => import('./withholdingTaxPage').then((module) => ({default: module.WithholdingTaxPage})));
const ExciseTaxPage = lazy(() => import('./exciseTaxPage').then((module) => ({default: module.ExciseTaxPage})));
const ZakatIncomeTaxPage = lazy(() => import('./zakatIncomeTaxPage').then((module) => ({default: module.ZakatIncomeTaxPage})));
const BudgetPage = lazy(() => import('./financePages').then((module) => ({default: module.BudgetPage})));
const TransactionsPage = lazy(() => import('./financePages').then((module) => ({default: module.TransactionsPage})));
const TreasuryPage = lazy(() => import('./financePages').then((module) => ({default: module.TreasuryPage})));
const LeasesPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.LeasesPage})));
const AssetsPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.AssetsPage})));
const PrepaidsPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.PrepaidsPage})));
const AccrualsPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.AccrualsPage})));
const ClosePage = lazy(() => import('./financePages').then((module) => ({default: module.ClosePage})));
const AssurancePage = lazy(() => import('./financePages').then((module) => ({default: module.AssurancePage})));
const CompliancePage = lazy(() => import('./financePages').then((module) => ({default: module.CompliancePage})));
const SecurityPage = lazy(() => import('./financePages').then((module) => ({default: module.SecurityPage})));
const FxPage = lazy(() => import('./financePages').then((module) => ({default: module.FxPage})));
const InventoryPage = lazy(() => import('./inventoryRealPage').then((module) => ({default: module.InventoryPage})));
const InventoryTraceabilityPage = lazy(() => import('./inventoryTraceabilityPage').then((module) => ({default: module.InventoryTraceabilityPage})));
const OperationalControlsPage = lazy(() => import('./operationalControlsPage').then((module) => ({default: module.OperationalControlsPage})));
const SalesPage = lazy(() => import('./salesPage').then((module) => ({default: module.SalesPage})));
const PurchasesPage = lazy(() => import('./purchasesPage').then((module) => ({default: module.PurchasesPage})));
const MaintenancePage = lazy(() => import('./maintenancePage').then((module) => ({default: module.MaintenancePage})));
const FleetPage = lazy(() => import('./fleetPage').then((module) => ({default: module.FleetPage})));
const LegalPage = lazy(() => import('./legalPage').then((module) => ({default: module.LegalPage})));
const CipProjectsPage = lazy(() => import('./cipProjectsPage').then((module) => ({default: module.CipProjectsPage})));
const ManualJournalsPage = lazy(() => import('./manualJournalsPage').then((module) => ({default: module.ManualJournalsPage})));
const ChartOfAccountsPage = lazy(() => import('./chartOfAccountsPage').then((module) => ({default: module.ChartOfAccountsPage})));
const DataResetPage = lazy(() => import('./dataResetPage').then((module) => ({default: module.DataResetPage})));
const ItemsPage = lazy(() => import('./itemsPage').then((module) => ({default: module.ItemsPage})));
const UsersPage = lazy(() => import('./usersPage').then((module) => ({default: module.UsersPage})));
const ReportsCenterPage = lazy(() => import('./reportsCenterPage').then((module) => ({default: module.ReportsCenterPage})));
const OpeningBalancesPage = lazy(() => import('./openingBalancesPage').then((module) => ({default: module.OpeningBalancesPage})));
const GymPage = lazy(() => import('./gymRealPage').then((module) => ({default: module.GymPage})));
const RestaurantPage = lazy(() => import('./restaurantRealPage').then((module) => ({default: module.RestaurantPage})));
const ManufacturingPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.ManufacturingPage})));
const QualityPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.QualityPage})));
const FoodSafetyPage = lazy(() => import('./foodSafetyRealPage').then((module) => ({default: module.FoodSafetyPage})));
const HrPage = lazy(() => import('./hrRealPage').then((module) => ({default: module.HrPage})));
const CrmPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.CrmPage})));
const AuditPage = lazy(() => import('./governanceRealPage').then((module) => ({default: module.AuditPage})));
const ItPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.ItPage})));
const AccessGovernancePage = lazy(() => import('./accessGovernanceRealPage').then((module) => ({default: module.AccessGovernancePage})));

export function DashboardRoutes({ar, companyId, scope, view, onNavigate}: {ar: boolean; companyId: number; scope: CompanyScope; view: View; onNavigate: (view: View) => void}) {
  const pages: Partial<Record<View, ReactNode>> = {
    workbench:<WorkspacePage ar={ar} companyId={companyId}/>, finalCompletion:<FinalCompletionPage ar={ar} companyId={companyId}/>,
    executive:<ExecutivePage ar={ar} companyId={scope} apiCompanyId={companyId} onNavigate={onNavigate}/>, core:<CorePage ar={ar} companyId={companyId}/>,
    finance:<FinancePage ar={ar} companyId={companyId}/>, aging:<AgingPage ar={ar} companyId={companyId}/>,
    returns:<CreditNotesPage ar={ar} companyId={companyId}/>,
    salesReturns:<CreditNotesPage ar={ar} companyId={companyId} fixedType="SALES"/>,
    purchaseReturns:<CreditNotesPage ar={ar} companyId={companyId} fixedType="PURCHASE"/>,
    openingBalances:<OpeningBalancesPage ar={ar} companyId={companyId}/>,
    withholdingTax:<WithholdingTaxPage ar={ar} companyId={companyId}/>,
    exciseTax:<ExciseTaxPage ar={ar} companyId={companyId}/>, zakatIncomeTax:<ZakatIncomeTaxPage ar={ar} companyId={companyId}/>,
    budget:<BudgetPage ar={ar} companyId={companyId}/>, transactions:<TransactionsPage ar={ar} companyId={companyId}/>,
    inventory:<InventoryPage ar={ar} companyId={companyId}/>, inventoryTraceability:<InventoryTraceabilityPage ar={ar} companyId={companyId}/>,
    operationalControls:<OperationalControlsPage ar={ar} companyId={companyId}/>, sales:<SalesPage ar={ar} companyId={companyId}/>,
    purchases:<PurchasesPage ar={ar} companyId={companyId}/>, maintenance:<MaintenancePage ar={ar} companyId={companyId}/>,
    fleet:<FleetPage ar={ar} companyId={companyId}/>, legal:<LegalPage ar={ar} companyId={companyId}/>,
    cipProjects:<CipProjectsPage ar={ar} companyId={companyId}/>, manualJournals:<ManualJournalsPage ar={ar} companyId={companyId}/>,
    chartOfAccounts:<ChartOfAccountsPage ar={ar} companyId={companyId}/>, dataReset:<DataResetPage ar={ar} companyId={companyId}/>,
    items:<ItemsPage ar={ar} companyId={companyId}/>, users:<UsersPage ar={ar} companyId={companyId}/>,
    reports:<ReportsCenterPage ar={ar} companyId={companyId}/>, crm:<CrmPage ar={ar} companyId={companyId}/>,
    treasury:<TreasuryPage ar={ar} companyId={companyId}/>, leases:<LeasesPage ar={ar} companyId={companyId}/>,
    assets:<AssetsPage ar={ar} companyId={companyId}/>, prepaids:<PrepaidsPage ar={ar} companyId={companyId}/>,
    accruals:<AccrualsPage ar={ar} companyId={companyId}/>, gym:<GymPage ar={ar} companyId={companyId}/>,
    restaurant:<RestaurantPage ar={ar} companyId={companyId}/>, manufacturing:<ManufacturingPage ar={ar} companyId={companyId}/>,
    quality:<QualityPage ar={ar} companyId={companyId}/>, foodSafety:<FoodSafetyPage ar={ar} companyId={companyId}/>,
    hr:<HrPage ar={ar} companyId={companyId}/>, close:<ClosePage ar={ar} companyId={companyId}/>,
    assurance:<AssurancePage ar={ar} companyId={companyId}/>, compliance:<CompliancePage ar={ar} companyId={companyId}/>,
    security:<SecurityPage ar={ar} companyId={companyId}/>, accessGovernance:<AccessGovernancePage ar={ar} companyId={companyId}/>,
    fx:<FxPage ar={ar} companyId={companyId}/>, audit:<AuditPage ar={ar} companyId={companyId}/>,
    it:<ItPage ar={ar} companyId={companyId}/>,
  };
  return <Suspense fallback={<div className="route-loading">{ar ? 'جارٍ تحميل الوحدة...' : 'Loading module...'}</div>}>
    {pages[view] || pages.executive}
  </Suspense>;
}
