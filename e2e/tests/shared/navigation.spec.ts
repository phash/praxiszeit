import { test, expect } from '../../fixtures/base.fixture';

test.describe('Navigation & Access Control', () => {
  test('employee sees no admin links', async ({ employeePage }) => {
    // Employee sidebar/navigation should NOT contain admin links
    await employeePage.goto('/');
    await employeePage.waitForLoadState('networkidle');

    // Verify employee nav items are visible
    await expect(employeePage.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(employeePage.getByRole('link', { name: 'Zeiterfassung' })).toBeVisible();

    // Verify admin-only items are NOT visible
    await expect(employeePage.getByRole('link', { name: 'Benutzerverwaltung' })).not.toBeVisible();
    await expect(employeePage.getByRole('link', { name: 'Berichte' })).not.toBeVisible();
    // The "Administration" section heading should not exist for employees
    await expect(employeePage.getByText('Administration')).not.toBeVisible();
  });

  test('admin pages redirect employee', async ({ employeePage }) => {
    // Try navigating to an admin page as employee
    await employeePage.goto('/admin/users');
    await employeePage.waitForLoadState('networkidle');

    // ProtectedRoute with requiredRole="admin" redirects non-admins to "/"
    await expect(employeePage).toHaveURL('http://localhost/');
  });

  test('admin sees admin navigation', async ({ adminPage }) => {
    await adminPage.goto('/');
    await adminPage.waitForLoadState('networkidle');

    // Admin should see the Administration section and admin nav items
    await expect(adminPage.getByText('Administration')).toBeVisible();
    await expect(adminPage.getByRole('link', { name: 'Benutzerverwaltung' })).toBeVisible();
    await expect(adminPage.getByRole('link', { name: 'Berichte' })).toBeVisible();
    await expect(adminPage.getByRole('link', { name: 'Fehler-Monitoring' })).toBeVisible();
  });

  test('mobile hamburger menu', async ({ employeePage }) => {
    // Set viewport to mobile size (below lg breakpoint = 1024px)
    await employeePage.setViewportSize({ width: 375, height: 667 });
    await employeePage.goto('/');
    await employeePage.waitForLoadState('networkidle');

    // On mobile, the sidebar is hidden (translated off-screen)
    // The nav links inside the sidebar should not be visible initially
    // (sidebar has -translate-x-full on mobile when closed)
    const dashboardLink = employeePage.getByRole('link', { name: 'Dashboard' });

    // The hamburger button has aria-label="Menü öffnen"
    const hamburgerButton = employeePage.getByRole('button', { name: 'Menü öffnen' });
    await expect(hamburgerButton).toBeVisible();

    // Click hamburger to open sidebar
    await hamburgerButton.click();

    // After clicking, navigation links should become visible
    await expect(dashboardLink).toBeVisible();
    await expect(employeePage.getByRole('link', { name: 'Zeiterfassung' })).toBeVisible();
    // Hilfe is a button (opens panel), not a link – check Abmelden button instead
    await expect(employeePage.getByRole('button', { name: 'Abmelden' })).toBeVisible();

    // Close button should be visible (aria-label="Menü schließen")
    const closeButton = employeePage.getByRole('button', { name: 'Menü schließen' });
    await expect(closeButton).toBeVisible();

    // Close the menu
    await closeButton.click();

    // Hamburger should be visible again
    await expect(hamburgerButton).toBeVisible();
  });
});
