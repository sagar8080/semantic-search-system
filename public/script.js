document.addEventListener('DOMContentLoaded', () => {
    console.log("Chainlit Custom Script Loaded!");

    // --- Smooth scroll for new messages ---
    // The main content area where messages are appended seems to be a child of
    // a div with class "flex-grow overflow-y-auto". This might be generic.
    // Let's try to find the direct parent of message steps.
    // The messages are within a div like:
    // <div class="flex flex-col mx-auto w-full flex-grow p-4" style="max-width: min(60rem, 100vw);">
    // which is inside <div class="relative flex flex-col flex-grow overflow-y-auto">
    // Let's target the latter one if it's consistent.
    const chatMessagesContainer = document.querySelector('div.relative.flex.flex-col.flex-grow.overflow-y-auto');

    if (chatMessagesContainer) {
        const observer = new MutationObserver((mutationsList, observer) => {
            for(const mutation of mutationsList) {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    // Scroll to the bottom with a smooth behavior
                    chatMessagesContainer.scrollTo({
                        top: chatMessagesContainer.scrollHeight,
                        behavior: 'smooth'
                    });
                }
            }
        });

        observer.observe(chatMessagesContainer, { childList: true, subtree: true });
        console.log("Smooth scroll observer attached to chat container.");
    } else {
        console.warn("Chat messages container for smooth scroll not found. Adjust selector if needed.");
    }

    // --- Enhance Input Area Focus ---
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('focus', () => {
            const composer = document.getElementById('message-composer');
            if (composer) {
                composer.style.boxShadow = '0 0 15px rgba(var(--ring-r), var(--ring-g), var(--ring-b), 0.5)'; // Use ring color variables
                composer.style.borderColor = 'rgb(var(--ring-r), var(--ring-g), var(--ring-b))'; // Use ring color variables
            }
        });
        chatInput.addEventListener('blur', () => {
            const composer = document.getElementById('message-composer');
            if (composer) {
                composer.style.boxShadow = 'none';
                composer.style.borderColor = 'var(--border)'; // Revert to default border
            }
        });
        console.log("Input area focus enhancements active.");
    }

    // --- Example: Add a subtle animation to new messages ---
    // This is more complex as it requires identifying new messages as they are added.
    // The MutationObserver above can be extended for this.
    // For now, this is a placeholder for how you might start.
    const observeNewMessages = (container) => {
        const messageObserver = new MutationObserver((mutationsList) => {
            for (const mutation of mutationsList) {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach(node => {
                        // Check if the added node is a message step
                        if (node.nodeType === 1 && node.getAttribute('data-step-type')) {
                            node.style.opacity = '0';
                            node.style.transform = 'translateY(10px)';
                            node.style.transition = 'opacity 0.3s ease-out, transform 0.3s ease-out';
                            setTimeout(() => {
                                node.style.opacity = '1';
                                node.style.transform = 'translateY(0)';
                            }, 50); // Slight delay to ensure it's in the DOM
                        }
                    });
                }
            }
        });
        messageObserver.observe(container, { childList: true });
        console.log("New message animation observer attached.");
    };

    if (chatMessagesContainer) { // Re-use the container from smooth scroll
        // Find the actual div where message steps are direct children
        const directMessageParent = chatMessagesContainer.querySelector('div.flex.flex-col.mx-auto.w-full.flex-grow.p-4');
        if (directMessageParent) {
            observeNewMessages(directMessageParent);
        }
    }

    // --- Dynamic Title Update (Example) ---
    let messageCount = 0;
    const originalTitle = document.title;
    const updateTitleWithNotification = () => {
        messageCount++;
        document.title = `(${messageCount}) ${originalTitle}`;
    };

    // Hook into when an assistant message might appear (this is a simplified example)
    // You'd likely tie this to an actual event or a more precise DOM change.
    // For now, let's just demonstrate resetting it on input focus.
    if (chatInput) {
        chatInput.addEventListener('focus', () => {
            messageCount = 0;
            document.title = originalTitle;
        });
    }
    // To actually trigger updateTitleWithNotification, you'd call it when an assistant sends a message.
    // This could be done by having your Python code send a small, hidden JS command via cl.Message
    // or by more complex DOM observation.

});
