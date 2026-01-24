// Custom JavaScript for Relace MCP documentation

// Add copy success feedback
document$.subscribe(function() {
  // Handle code copy button clicks
  const copyButtons = document.querySelectorAll('.md-clipboard');
  copyButtons.forEach(button => {
    button.addEventListener('click', function() {
      // Visual feedback already handled by Material theme
      console.log('Code copied to clipboard');
    });
  });
});
