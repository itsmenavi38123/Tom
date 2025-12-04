// Form handling and real-time preview updates
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('datasetForm');
    const generateBtn = document.getElementById('generateBtn');
    const loadingOverlay = document.getElementById('loadingOverlay');

    // Update preview stats in real-time
    function updatePreviewStats() {
        const months = parseInt(document.getElementById('months').value) || 0;
        const bankTx = parseInt(document.getElementById('bank_txn_per_month').value) || 0;
        const ccTx = parseInt(document.getElementById('cc_txn_per_month').value) || 0;
        const customers = parseInt(document.getElementById('num_customers').value) || 0;
        const vendors = parseInt(document.getElementById('num_vendors').value) || 0;
        const invoices = parseInt(document.getElementById('num_invoices').value) || 0;

        const totalTransactions = (bankTx + ccTx) * months;
        const totalEntities = customers + vendors;

        document.getElementById('totalTransactions').textContent = totalTransactions.toLocaleString();
        document.getElementById('totalEntities').textContent = totalEntities.toLocaleString();
        document.getElementById('timePeriod').textContent = `${months} month${months !== 1 ? 's' : ''}`;
    }

    // Fix savings account field operability
    function setupSavingsAccountToggle() {
        const savingsCheckbox = document.querySelector('input[name="include_savings_account"]');
        const savingsAccountsInput = document.getElementById('num_savings_accounts');
        
        if (savingsCheckbox && savingsAccountsInput) {
            // Sync checkbox state when number changes
            savingsAccountsInput.addEventListener('input', function() {
                const numValue = parseInt(this.value) || 0;
                savingsCheckbox.checked = numValue > 0;
                updatePreviewStats();
            });
            
            // Sync number field when checkbox changes
            savingsCheckbox.addEventListener('change', function() {
                if (!this.checked && parseInt(savingsAccountsInput.value) > 0) {
                    savingsAccountsInput.value = '0';
                }
                updatePreviewStats();
            });
        }
    }

    // Setup output file checkboxes
    function setupOutputFiles() {
const defaultFiles = ['customers', 'vendors', 'products', 'chart_of_accounts', 'invoices', 'bank', 'creditcard'];
        
        defaultFiles.forEach(file => {
            const checkbox = document.querySelector(`input[value="${file}"]`);
            if (checkbox) {
                checkbox.checked = true;
            }
        });
    }

    // Attach event listeners to all inputs
    document.querySelectorAll('input, select').forEach(input => {
        input.addEventListener('input', updatePreviewStats);
        input.addEventListener('change', updatePreviewStats);
    });

    // Initialize everything
    updatePreviewStats();
    setupSavingsAccountToggle();
    setupOutputFiles();

    // Form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        if (!validateForm()) {
            return;
        }
        
        const submitBtn = generateBtn;
        const loadingSpinner = document.getElementById('btnLoading');
        
        // Show loading state
        submitBtn.disabled = true;
        loadingSpinner.style.display = 'inline-block';
        loadingOverlay.style.display = 'flex';

        try {
            // Collect form data
            const formData = new FormData(form);
            
            // Handle checkbox groups
            const outputFiles = [];
            document.querySelectorAll('input[name="output_files"]:checked').forEach(checkbox => {
                outputFiles.push(checkbox.value);
            });
            
            // Clear existing output_files entries and add fresh ones
            formData.delete('output_files');
            outputFiles.forEach(file => formData.append('output_files', file));

            // Send request
            const response = await fetch('/api/generate', {
                method: 'POST',
                body: formData
            });

            // Check if response is OK before trying to parse
            if (!response.ok) {
                let errorMessage = `HTTP error! status: ${response.status}`;
                try {
                    const errorText = await response.text();
                    if (errorText) {
                        try {
                            const errorData = JSON.parse(errorText);
                            errorMessage = errorData.detail || errorData.message || errorText;
                        } catch (e) {
                            errorMessage = errorText;
                        }
                    }
                } catch (e) {
                    errorMessage = `${response.status}: ${response.statusText}`;
                }
                throw new Error(errorMessage);
            }

            // Check content type to ensure it's a zip file
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/zip')) {
                const errorText = await response.text();
                throw new Error(`Expected ZIP file but got: ${contentType}. Server response: ${errorText.substring(0, 200)}...`);
            }

            // Create download
            const blob = await response.blob();
            
            if (blob.size === 0) {
                throw new Error('Received empty file from server');
            }
            
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            
            const clientName = document.getElementById('client_name').value || 'dataset';
            const timestamp = new Date().toISOString().slice(0,10);
            a.download = `bookdash_dataset_${clientName.replace(/\s+/g, '_')}_${timestamp}.zip`;
            
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);

            showNotification('Dataset generated successfully! Download started.', 'success');

        } catch (error) {
            console.error('Error:', error);
            let errorMessage = error.message;
            
            if (errorMessage.includes('500 Internal Server Error')) {
                errorMessage = 'Server error: Please check the server logs for details.';
            } else if (errorMessage.includes('Failed to fetch')) {
                errorMessage = 'Network error: Please check your connection and try again.';
            }
            
            showNotification('Error generating dataset: ' + errorMessage, 'error');
        } finally {
            submitBtn.disabled = false;
            loadingSpinner.style.display = 'none';
            loadingOverlay.style.display = 'none';
        }
    });

    // Range input helpers
    document.querySelectorAll('input[type="number"]').forEach(input => {
        const min = parseInt(input.min) || 0;
        const max = parseInt(input.max) || 100;

        input.addEventListener('blur', function() {
            if (this.value !== '') {
                let val = parseInt(this.value);
                if (!isNaN(val)) {
                    if (val < min) this.value = min;
                    if (val > max) this.value = max;
                }
            }
            updatePreviewStats();
        });
    });

    // Industry-specific presets
    function applyIndustryPreset(industry) {
        const presets = {
            'wellness': { 
                num_customers: 20, 
                num_products: 6, 
                bank_txn_per_month: 120, 
                num_invoices: 30,
                num_vendors: 15
            },
            'retail': { 
                num_customers: 30, 
                num_products: 15, 
                bank_txn_per_month: 200, 
                num_invoices: 50,
                num_vendors: 20
            },
            'ecommerce': { 
                num_customers: 50, 
                num_products: 8, 
                bank_txn_per_month: 150, 
                num_invoices: 80,
                num_vendors: 12
            },
            'restaurant': { 
                num_customers: 40, 
                num_products: 12, 
                bank_txn_per_month: 180, 
                num_invoices: 60,
                num_vendors: 18
            },
            'services': { 
                num_customers: 15, 
                num_products: 5, 
                bank_txn_per_month: 80, 
                num_invoices: 20,
                num_vendors: 10
            },
            'nonprofit': { 
                num_customers: 25, 
                num_products: 3, 
                bank_txn_per_month: 100, 
                num_invoices: 15,
                num_vendors: 12
            },
            'custom': { 
                num_customers: 15, 
                num_products: 8, 
                bank_txn_per_month: 100, 
                num_invoices: 25,
                num_vendors: 12
            }
        };
        
        const preset = presets[industry] || presets.custom;
        Object.keys(preset).forEach(field => {
            const input = document.getElementById(field);
            if (input) {
                input.value = preset[field];
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }

    // Apply industry preset when industry changes
    const industrySelect = document.getElementById('industry');
    if (industrySelect) {
        industrySelect.addEventListener('change', function() {
            applyIndustryPreset(this.value);
        });
        
        applyIndustryPreset(industrySelect.value);
    }

    // Add input animations
    document.querySelectorAll('input, select').forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.classList.add('focused');
        });
        
        input.addEventListener('blur', function() {
            this.parentElement.classList.remove('focused');
        });
    });

    // Add character counter for client name
    const clientNameInput = document.getElementById('client_name');
    if (clientNameInput) {
        clientNameInput.addEventListener('input', function() {
            const maxLength = 80;
            const currentLength = this.value.length;
            let counter = this.nextElementSibling;
            
            if (!counter || !counter.classList.contains('char-counter')) {
                counter = document.createElement('div');
                counter.className = 'char-counter';
                this.parentElement.appendChild(counter);
            }
            
            counter.textContent = `${currentLength}/${maxLength}`;
            counter.style.color = currentLength > maxLength ? '#e53e3e' : '#718096';
            counter.style.fontSize = '0.8rem';
            counter.style.marginTop = '5px';
        });
        
        // Trigger initial count
        clientNameInput.dispatchEvent(new Event('input'));
    }
});

function validateForm() {
    const clientName = document.getElementById('client_name').value;
    if (!clientName || clientName.trim().length === 0) {
        showNotification('Please enter a client name', 'error');
        return false;
    }
    
    const startDate = document.getElementById('start_date').value;
    if (!startDate) {
        showNotification('Please select a start date', 'error');
        return false;
    }
    
    // Check if at least one output file is selected
    const checkedFiles = document.querySelectorAll('input[name="output_files"]:checked');
    if (checkedFiles.length === 0) {
        showNotification('Please select at least one output file type', 'error');
        return false;
    }
    
    return true;
}

function showNotification(message, type = 'info') {
    document.querySelectorAll('.notification').forEach(notif => notif.remove());
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="background: none; border: none; color: white; font-size: 1.2rem; cursor: pointer;">×</button>
    `;
    
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'error' ? '#f56565' : type === 'success' ? '#48bb78' : '#4299e1'};
        color: white;
        border-radius: 5px;
        z-index: 1000;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        display: flex;
        align-items: center;
        gap: 10px;
        max-width: 400px;
        word-wrap: break-word;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}