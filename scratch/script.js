document.addEventListener('DOMContentLoaded', () => {
    const taskInput = document.getElementById('taskInput');
    const addTaskBtn = document.getElementById('addTaskBtn');
    const taskList = document.getElementById('taskList');

    addTaskBtn.addEventListener('click', addTask);
    taskList.addEventListener('click', handleTaskActions);

    function addTask() {
        const taskText = taskInput.value.trim();
        if (taskText === '') return;

        const listItem = document.createElement('li');
        listItem.innerHTML = `
            <span>${taskText}</span>
            <div>
                <button class="complete-btn">Complete</button>
                <button class="delete-btn">Delete</button>
            </div>
        `;
        taskList.appendChild(listItem);
        taskInput.value = '';
    }

    function handleTaskActions(event) {
        const target = event.target;
        if (target.classList.contains('delete-btn')) {
            target.closest('li').remove();
        } else if (target.classList.contains('complete-btn')) {
            target.closest('li').classList.toggle('completed');
        }
    }
});