// Comments Component JavaScript (独立 - 削除可能)

document.addEventListener('DOMContentLoaded', function() {
    const commentForm = document.getElementById('commentForm');
    const commentInput = document.getElementById('commentInput');
    const charCount = document.getElementById('charCount');
    const commentsList = document.getElementById('commentsList');
    const commentCount = document.getElementById('comment-count');

    // 文字数カウント
    if (commentInput) {
        commentInput.addEventListener('input', function() {
            charCount.textContent = this.value.length;
        });
    }

    // コメント投稿
    if (commentForm) {
        commentForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const text = commentInput.value.trim();

            if (!text) {
                return;
            }

            // サーバーに送信
            fetch('/api/comment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: 'comment_text=' + encodeURIComponent(text)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    commentInput.value = '';
                    charCount.textContent = '0';
                } else {
                    alert('コメント投稿に失敗しました: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error posting comment:', error);
                alert('コメント投稿エラー');
            });
        });
    }

    // Socket.io: 新しいコメント受信
    if (typeof socket !== 'undefined') {
        socket.on('new_comment', function(data) {
            addCommentToList(data);
        });
    }

    // ページロード時にコメント履歴を取得
    fetch('/api/comments?limit=50')
        .then(response => response.json())
        .then(data => {
            if (data.comments && Array.isArray(data.comments)) {
                data.comments.forEach(comment => {
                    addCommentToList(comment, false);
                });
            }
        })
        .catch(error => console.error('Error loading comments:', error));

    // コメント表示関数
    function addCommentToList(comment, isNew = true) {
        const commentDiv = document.createElement('div');
        commentDiv.className = 'comment-item' + (isNew ? ' new-comment' : '');
        commentDiv.id = 'comment-' + comment.comment_id;

        commentDiv.innerHTML = `
            <div class="comment-header">
                <span class="comment-team-name">${escapeHtml(comment.team_name)}</span>
                <span class="comment-time">${comment.created_at}</span>
            </div>
            <div class="comment-text">${escapeHtml(comment.comment_text)}</div>
        `;

        commentsList.appendChild(commentDiv);

        // コメント数を更新
        updateCommentCount();

        // 新しいコメントの場合、一時的にハイライト
        if (isNew) {
            setTimeout(() => {
                commentDiv.classList.remove('new-comment');
            }, 2000);
        }
    }

    // コメント数カウント表示
    function updateCommentCount() {
        const count = commentsList.querySelectorAll('.comment-item').length;
        if (commentCount) {
            commentCount.textContent = count + ' 件';
        }
    }

    // HTML エスケープ（XSS対策）
    function escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
});
