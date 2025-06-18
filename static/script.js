document.addEventListener('DOMContentLoaded', () => {
    if (typeof firebase === 'undefined' || typeof firebase.auth === 'undefined') {
        console.error("Firebase SDK не загружен!");
        alert("Ошибка загрузки приложения. Пожалуйста, перезагрузите страницу.");
        return;
    }
    if (!currentUserUid) {
        console.warn("currentUserUid не определен. Пользователь не аутентифицирован сервером.");
        return;
    }

    const fbAuthInstance = firebase.auth();
    const socket = io({
        autoConnect: false
    });
    fbAuthInstance.onAuthStateChanged(user => {
        if (user && currentUserUid === user.uid) {
            console.log('JS (script.js): Firebase user confirmed, (re)connecting to Socket.IO');
            if (!socket.connected) {
                socket.connect();
            }
        } else if (user && currentUserUid !== user.uid) {
            console.warn('JS (script.js): Mismatch UID. Firebase UID:', user.uid, 'Flask UID:', currentUserUid);
            window.location.href = '/logout';
        } else if (!user && currentUserUid) {
            console.warn('JS (script.js): Firebase user absent, but Flask session exists. Redirecting to logout.');
            window.location.href = '/logout';
        }
    });
    const searchUserInput = document.getElementById('search-user');
    const chatListDiv = document.getElementById('chat-list');
    const messagesContainer = document.getElementById('messages-container');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatHeaderBar = document.getElementById('chat-header');
    const chatPartnerAvatarImg = document.getElementById('chat-partner-avatar');
    const chatWithInfoSpan = document.getElementById('chat-with-info');
    const messageInputArea = document.getElementById('message-input-area');
    const selectChatPrompt = document.getElementById('select-chat-prompt');
    const mainMenuButton = document.getElementById('main-menu-button');
    const mainMenuPanel = document.getElementById('main-menu-panel');
    const chatContainer = document.querySelector('.chat-container');
    const chatArea = document.getElementById('chat-area');
    const backToChatListButton = document.getElementById('back-to-chat-list-button');
    const sidebar = document.getElementById('sidebar');
    const resizeHandle = document.getElementById('resize-handle');
    const logoutButton = document.querySelector('.menu-logout');

    let currentChatPartner = null;
    let isResizing = false;
    let searchMode = false;

    function isMobileView() {
        return window.innerWidth <= 768;
    }

    function adjustLayoutForVisualViewport() {
        if (isMobileView() && chatArea && chatContainer.classList.contains('mobile-chat-view-active')) {
            if (window.visualViewport) {
                chatArea.style.height = `${window.visualViewport.height}px`;
            } else {
                chatArea.style.height = `${window.innerHeight}px`;
            }
        } else if (chatArea) {
            chatArea.style.height = '';
        }
    }

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', adjustLayoutForVisualViewport);
    }
    window.addEventListener('resize', () => {
        adjustLayoutForVisualViewport();
        if (isMobileView()) {
            if (resizeHandle) resizeHandle.style.display = 'none';
            if (sidebar) sidebar.style.width = '';
            if (isResizing) {
                isResizing = false; document.body.style.cursor = 'default'; document.body.style.userSelect = 'auto';
            }
        } else {
            if (resizeHandle) resizeHandle.style.display = 'block';
            if (sidebar && localStorage.getItem('sidebarWidth')) {
                sidebar.style.width = localStorage.getItem('sidebarWidth');
            }
        }
    });
    window.addEventListener('load', () => {
        adjustLayoutForVisualViewport();
        if (sidebar && !isMobileView() && localStorage.getItem('sidebarWidth')) {
            sidebar.style.width = localStorage.getItem('sidebarWidth');
        } else if (isMobileView() && resizeHandle) {
            resizeHandle.style.display = 'none';
        }
    });

    socket.on('connect', () => {
        console.log('JS: Подключено к Socket.IO');
        loadUserChats();
        if (sidebar && !isMobileView() && localStorage.getItem('sidebarWidth')) {
            sidebar.style.width = localStorage.getItem('sidebarWidth');
        }
    });

    socket.on('disconnect', (reason) => {
        console.log('JS: Отключено от Socket.IO. Причина:', reason);
        if (reason === 'io server disconnect') {
            alert('Соединение с сервером разорвано. Пожалуйста, войдите снова.');
            window.location.href = "/logout";
        }
    });
    socket.on('error', (data) => {
        console.error('JS Socket.IO Ошибка: ', data.message);
    });

    socket.on('new_message', (data) => {
        console.log('JS: Получено new_message', data);
        const isMyMessage = data.senderUid === currentUserUid;
        const chatPartnerInvolvedUsername = isMyMessage ? data.recipient : data.sender;

        let partnerDetailsForList;
        if (isMyMessage) {
            if (currentChatPartner && currentChatPartner.username === data.recipient) {
                 partnerDetailsForList = currentChatPartner;
            } else {
                const existingUserItem = chatListDiv.querySelector(`.user-item[data-username="${data.recipient}"]`);
                if (existingUserItem && existingUserItem.dataset.uid) {
                    partnerDetailsForList = {
                        username: data.recipient,
                        displayName: existingUserItem.querySelector('.user-item-name').textContent,
                        avatarUrl: existingUserItem.querySelector('.user-item-avatar').src,
                        uid: existingUserItem.dataset.uid
                    };
                } else {
                }
            }
        } else {
            partnerDetailsForList = { username: data.sender, displayName: data.senderDisplayName, avatarUrl: data.senderAvatarUrl, uid: data.senderUid };
        }
        if (currentChatPartner && currentChatPartner.username === chatPartnerInvolvedUsername) {
            appendMessage(data.senderDisplayName, data.content, data.timestamp, isMyMessage, data.senderAvatarUrl, true);
            if (partnerDetailsForList) {
                updateChatInList(chatPartnerInvolvedUsername, data, true, partnerDetailsForList);
            } else { 
                 fetchUserDetailsForListUpdate(chatPartnerInvolvedUsername, data, true);
            }
        } else if (data.recipient === currentUsername) { 
            updateChatInList(data.sender, data, false, partnerDetailsForList);
        } else if (isMyMessage) {
             if (partnerDetailsForList) {
                updateChatInList(data.recipient, data, false, partnerDetailsForList);
             } else {
                fetchUserDetailsForListUpdate(data.recipient, data, false);
             }
        }
    });

    async function fetchUserDetailsForListUpdate(partnerUsername, lastMessageObject, isActiveChat) {
        try {
            const response = await fetch(`/search_users?query=${encodeURIComponent(partnerUsername.substring(1))}`);
            if (response.ok) {
                const users = await response.json();
                const details = users.find(u => u.username === partnerUsername);
                if (details) {
                    updateChatInList(partnerUsername, lastMessageObject, isActiveChat, details);
                } else {
                    updateChatInList(partnerUsername, lastMessageObject, isActiveChat, { username: partnerUsername, displayName: partnerUsername, avatarUrl: defaultAvatarUrlGlobal, uid: null });
                }
            }
        } catch (error) {
            console.error(`JS: Ошибка получения деталей для ${partnerUsername} при обновлении списка:`, error);
             updateChatInList(partnerUsername, lastMessageObject, isActiveChat, { username: partnerUsername, displayName: partnerUsername, avatarUrl: defaultAvatarUrlGlobal, uid: null });
        }
    }
    if (mainMenuButton) {
        mainMenuButton.addEventListener('click', (event) => {
            event.stopPropagation();
            if (mainMenuPanel) mainMenuPanel.style.display = mainMenuPanel.style.display === 'none' ? 'block' : 'none';
        });
    }
    document.addEventListener('click', (event) => {
        if (mainMenuPanel && mainMenuButton &&
            mainMenuPanel.style.display === 'block' &&
            !mainMenuPanel.contains(event.target) &&
            !mainMenuButton.contains(event.target)) {
            mainMenuPanel.style.display = 'none';
        }
    });
    if (logoutButton) {
        logoutButton.addEventListener('click', async (e) => {
            e.preventDefault();
            try {
                if (fbAuthInstance) {
                    await fbAuthInstance.signOut();
                    console.log('JS: Пользователь вышел из Firebase.');
                }
                window.location.href = e.target.href;
            } catch (error) {
                console.error('JS: Ошибка выхода из Firebase:', error);
                window.location.href = e.target.href;
            }
        });
    }

    async function loadUserChats() {
        if (!socket.connected && fbAuthInstance.currentUser) {
             console.log("JS: Socket не подключен в loadUserChats, ожидаем подключения...");
             return;
        }
         if (!fbAuthInstance.currentUser) {
            console.log("JS: Нет пользователя Firebase в loadUserChats.");
            return;
        }
        console.log('JS: Загрузка списка чатов пользователя...');
        try {
            const response = await fetch(`/get_user_chats`);
            if (!response.ok) {
                console.error('JS: Ошибка загрузки списка чатов:', response.status, response.statusText);
                if (response.status === 401) { window.location.href = "/logout"; }
                return;
            }
            const chats = await response.json();
            if (chatListDiv) chatListDiv.innerHTML = '';
            if (chats.length > 0) {
                if (selectChatPrompt) selectChatPrompt.style.display = 'none';
            } else {
                if (selectChatPrompt) {
                    selectChatPrompt.textContent = "У вас пока нет чатов. Найдите собеседника.";
                    selectChatPrompt.style.display = 'block';
                }
            }
            chats.forEach(chatPartner => { 
                displayUserInList(chatPartner, 'chat', chatPartner.lastMessage, false);
            });
        } catch (error) {
            console.error('JS: Исключение при запросе списка чатов:', error);
        }
    }
    function updateChatInList(partnerUsername, lastMessageObject, isActiveChat, partnerDetailsInput) {
        if (!chatListDiv || !partnerDetailsInput || !partnerDetailsInput.username) {
             console.warn("JS: updateChatInList - отсутствуют необходимые элементы или данные", {partnerUsername, partnerDetailsInput});
             return;
        }
        let existingChatItem = chatListDiv.querySelector(`.user-item[data-username="${partnerUsername}"]`);

        if (existingChatItem) {
            const lastMsgSpan = existingChatItem.querySelector('.user-item-last-msg');
            if (lastMsgSpan && lastMessageObject && lastMessageObject.content) {
                let prefix = lastMessageObject.sender === currentUsername ? "Вы: " : "";
                lastMsgSpan.textContent = prefix + lastMessageObject.content.substring(0, 25) + (lastMessageObject.content.length > 25 ? '...' : '');
            }
            if (!isActiveChat || (currentChatPartner && currentChatPartner.username !== partnerUsername)) {
                if (!existingChatItem.classList.contains('has-unread')) { existingChatItem.classList.add('has-unread'); }
            } else { existingChatItem.classList.remove('has-unread'); }
            chatListDiv.prepend(existingChatItem);
        } else {
             displayUserInList(partnerDetailsInput, 'chat', lastMessageObject, !isActiveChat);
        }
    }
    if (searchUserInput) {
        searchUserInput.addEventListener('input', async () => {
            const query = searchUserInput.value.trim();
            if (query.length > 0) {
                searchMode = true;
                if (chatListDiv) chatListDiv.innerHTML = '';
                if (selectChatPrompt) selectChatPrompt.style.display = 'none';
                try {
                    const response = await fetch(`/search_users?query=${encodeURIComponent(query)}`);
                    if (!response.ok) {
                        console.error('JS: Ошибка поиска пользователей:', response.statusText);
                        if (chatListDiv) chatListDiv.innerHTML = '<p class="no-results">Ошибка при поиске.</p>';
                        return;
                    }
                    const users = await response.json();
                    if (users.length === 0) {
                        if (chatListDiv) chatListDiv.innerHTML = '<p class="no-results">Пользователи не найдены.</p>';
                    }
                    users.forEach(user => displayUserInList(user, 'search', null, false));
                } catch (error) {
                    console.error('JS: Исключение при запросе поиска:', error);
                    if (chatListDiv) chatListDiv.innerHTML = '<p class="no-results">Ошибка при поиске.</p>';
                }
            } else {
                searchMode = false;
                loadUserChats();
            }
        });
    }
    function displayUserInList(userData, type, lastMessageObject = null, hasUnread = false) {
        if (!userData || !userData.username || !chatListDiv) {
            console.warn("JS: displayUserInList - userData, userData.username или chatListDiv отсутствует", userData);
            return;
        }
        let existingItem = null;
        if (type === 'chat') {
            existingItem = chatListDiv.querySelector(`.user-item[data-username="${userData.username}"]`);
        }

        const userDiv = existingItem || document.createElement('div');
        if (!existingItem) {
            userDiv.classList.add('user-item');
            userDiv.dataset.username = userData.username;
            if(userData.uid) userDiv.dataset.uid = userData.uid;
        }

        if (hasUnread && type === 'chat') userDiv.classList.add('has-unread');
        else userDiv.classList.remove('has-unread');

        let avatarImg = userDiv.querySelector('.user-item-avatar');
        if (!avatarImg) {
            avatarImg = document.createElement('img');
            avatarImg.classList.add('user-item-avatar');
            userDiv.appendChild(avatarImg);
        }
        avatarImg.src = userData.avatarUrl || defaultAvatarUrlGlobal;
        avatarImg.alt = userData.displayName || userData.username;
        avatarImg.onerror = function() { this.src = defaultAvatarUrlGlobal; };

        let userInfoDiv = userDiv.querySelector('.user-item-info');
        if (!userInfoDiv) {
            userInfoDiv = document.createElement('div');
            userInfoDiv.classList.add('user-item-info');
            userDiv.appendChild(userInfoDiv);
        } else {
            userInfoDiv.innerHTML = '';
        }

        const displayNameSpan = document.createElement('span');
        displayNameSpan.classList.add('user-item-name');
        displayNameSpan.textContent = userData.displayName || userData.username;
        userInfoDiv.appendChild(displayNameSpan);

        if (type === 'search') {
            const usernameSpan = document.createElement('span');
            usernameSpan.classList.add('user-item-username');
            usernameSpan.textContent = userData.username;
            userInfoDiv.appendChild(usernameSpan);
        } else if (type === 'chat') {
            const lastMsgSpan = document.createElement('span');
            lastMsgSpan.classList.add('user-item-last-msg');
            if (lastMessageObject && lastMessageObject.content) {
                let prefix = lastMessageObject.sender === currentUsername ? "Вы: " : "";
                lastMsgSpan.textContent = prefix + lastMessageObject.content.substring(0, 25) + (lastMessageObject.content.length > 25 ? '...' : '');
            } else {
                lastMsgSpan.textContent = 'Нет сообщений';
            }
            userInfoDiv.appendChild(lastMsgSpan);
        }

        if (!existingItem) {
            userDiv.addEventListener('click', () => {
                openChatWithUser(userData);
            });
            if (type === 'chat') chatListDiv.prepend(userDiv);
            else chatListDiv.appendChild(userDiv);
        } else if (type === 'chat') {
            chatListDiv.prepend(userDiv);
        }
    }

    async function openChatWithUser(partnerData) {
        if (!partnerData || !partnerData.username || !partnerData.uid) {
            console.error("JS: openChatWithUser - неверные данные партнера", partnerData);
            return;
        }
        console.log('JS: Открытие чата с:', partnerData);

        document.querySelectorAll('#chat-list .user-item.active').forEach(el => el.classList.remove('active'));
        const activeUserItemInList = chatListDiv.querySelector(`.user-item[data-username="${partnerData.username}"]`);
        if (activeUserItemInList) {
            activeUserItemInList.classList.add('active');
            activeUserItemInList.classList.remove('has-unread');
        }

        if (currentChatPartner && currentChatPartner.uid === partnerData.uid && chatContainer.classList.contains('mobile-chat-view-active') && isMobileView()) {
            console.log('JS: Чат с этим партнером (UID:', partnerData.uid, ') уже открыт в мобильном виде.');
            return;
        }
        currentChatPartner = partnerData;

        if (chatHeaderBar) chatHeaderBar.style.display = 'flex';
        if (chatPartnerAvatarImg) {
            chatPartnerAvatarImg.src = partnerData.avatarUrl || defaultAvatarUrlGlobal;
            chatPartnerAvatarImg.onerror = function() { this.src = defaultAvatarUrlGlobal; };
        }
        if (chatWithInfoSpan) chatWithInfoSpan.textContent = partnerData.displayName || partnerData.username;
        if (messagesContainer) messagesContainer.innerHTML = '';
        if (messageInputArea) messageInputArea.style.display = 'flex';
        if (selectChatPrompt) selectChatPrompt.style.display = 'none';

        if (isMobileView()) {
            if (chatContainer && !chatContainer.classList.contains('mobile-chat-view-active')) {
                chatContainer.classList.add('mobile-chat-view-active');
            }
            adjustLayoutForVisualViewport();
            setTimeout(() => { if (messageInput) messageInput.focus(); }, 50);
        } else {
            if (messageInput) messageInput.focus();
            if (chatArea) chatArea.style.height = '';
        }

        try {
            const response = await fetch(`/get_chat_history/${encodeURIComponent(partnerData.username)}`);
            if (!response.ok) {
                console.error('JS: Ошибка загрузки истории чата:', response.statusText); return;
            }
            const responseData = await response.json();
            const history = responseData.messages;
            currentChatPartner = responseData.partnerDetails || currentChatPartner;

            history.forEach(msg => {
                const isOwn = msg.senderUid === currentUserUid;
                appendMessage(msg.senderDisplayName, msg.content, msg.timestamp, isOwn, msg.senderAvatarUrl, false);
            });
        } catch (error) {
            console.error('JS: Исключение при запросе истории чата:', error);
        }
    }

    if (backToChatListButton) {
        backToChatListButton.addEventListener('click', () => {
            if (isMobileView()) {
                if (chatContainer.classList.contains('mobile-chat-view-active')) {
                    chatContainer.classList.remove('mobile-chat-view-active');
                }
                if (chatHeaderBar) chatHeaderBar.style.display = 'none';
                if (messageInputArea) messageInputArea.style.display = 'none';
                if (messagesContainer) messagesContainer.innerHTML = '';
                if (selectChatPrompt) {
                     selectChatPrompt.textContent = "Выберите чат для начала общения или найдите нового собеседника.";
                     selectChatPrompt.style.display = 'block';
                }
                currentChatPartner = null;
                document.querySelectorAll('#chat-list .user-item.active').forEach(el => el.classList.remove('active'));
                if (chatArea) chatArea.style.height = '';
            }
        });
    }

    if (sendButton) sendButton.addEventListener('click', sendMessage);
    if (messageInput) {
        messageInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
        });
    }

    function sendMessage() {
        if (!messageInput || !currentChatPartner || !currentChatPartner.username) return;
        const messageText = messageInput.value.trim();
        if (messageText) {
            const messageData = {
                recipient: currentChatPartner.username,
                message: messageText,
                timestamp: new Date().toISOString()
            };
            socket.emit('send_message', messageData);
            messageInput.value = '';
            messageInput.focus();
            if (isMobileView()) { setTimeout(adjustLayoutForVisualViewport, 50); }
        }
    }

    function appendMessage(senderDisplayName, content, timestamp, isOwnMessage, avatarUrl, isNewMessage = false) {
        if (!messagesContainer) return;
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message');
        if (isOwnMessage) messageDiv.classList.add('own-message');

        const avatarImg = document.createElement('img');
        avatarImg.src = avatarUrl || defaultAvatarUrlGlobal;
        avatarImg.alt = senderDisplayName || 'User';
        avatarImg.classList.add('message-avatar');
        avatarImg.onerror = function() { this.src = defaultAvatarUrlGlobal; };

        const messageBubble = document.createElement('div');
        messageBubble.classList.add('message-bubble');

        const senderSpan = document.createElement('span');
        senderSpan.classList.add('message-sender');
        senderSpan.textContent = senderDisplayName || 'Пользователь';

        const contentP = document.createElement('p');
        contentP.classList.add('message-content');
        contentP.textContent = content;

        const timeSpan = document.createElement('span');
        timeSpan.classList.add('message-time');
        timeSpan.textContent = new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        messageBubble.appendChild(senderSpan); messageBubble.appendChild(contentP); messageBubble.appendChild(timeSpan);

        if (isOwnMessage) { messageDiv.appendChild(messageBubble); messageDiv.appendChild(avatarImg); }
        else { messageDiv.appendChild(avatarImg); messageDiv.appendChild(messageBubble); }
        messagesContainer.appendChild(messageDiv);

        if (isNewMessage) {
            requestAnimationFrame(() => { requestAnimationFrame(() => { messageDiv.classList.add('message-visible'); }); });
        } else { messageDiv.classList.add('message-visible'); }

        if (messagesContainer.scrollTo) {
            messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: isNewMessage ? 'smooth' : 'auto' });
        } else { messagesContainer.scrollTop = messagesContainer.scrollHeight; }
    }

    if (resizeHandle && sidebar) {
        let initialSidebarWidth = 0; let startX = 0;
        const computedStyle = window.getComputedStyle(sidebar);
        let minWidth = parseInt(computedStyle.minWidth, 10);
        let maxWidth = parseInt(computedStyle.maxWidth, 10);
        if (isNaN(minWidth) || minWidth <= 0) minWidth = 200;
        if (isNaN(maxWidth) || maxWidth < minWidth) maxWidth = Math.max(minWidth, 500);

        const boundMouseMove = (e) => {
            if (!isResizing || isMobileView()) return;
            const deltaX = e.clientX - startX;
            let newWidth = initialSidebarWidth + deltaX;
            if (newWidth < minWidth) newWidth = minWidth;
            if (newWidth > maxWidth) newWidth = maxWidth;
            sidebar.style.width = `${newWidth}px`;
        };
        const boundMouseUp = () => {
            if (!isResizing) return;
            isResizing = false;
            document.body.style.cursor = 'default';
            document.body.style.userSelect = 'auto';
            if (!isMobileView()) { localStorage.setItem('sidebarWidth', sidebar.style.width); }
            document.removeEventListener('mousemove', boundMouseMove);
            document.removeEventListener('mouseup', boundMouseUp);
        };
        resizeHandle.addEventListener('mousedown', (e) => {
            if (isMobileView()) { if (resizeHandle) resizeHandle.style.display = 'none'; return; }
            if (resizeHandle) resizeHandle.style.display = 'block';
            e.preventDefault(); isResizing = true; startX = e.clientX; initialSidebarWidth = sidebar.offsetWidth;
            document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', boundMouseMove);
            document.addEventListener('mouseup', boundMouseUp);
        });
        if (isMobileView()) { if (resizeHandle) resizeHandle.style.display = 'none'; }
        else { if (resizeHandle) resizeHandle.style.display = 'block'; }
    }
});