(() => {
	const configUrl = document.getElementById("screen-config").dataset.url;
	const frame = document.getElementById("screen-frame");
	const status = document.getElementById("screen-status");
	const pollInterval = 15_000;

	let configuration = null;
	let currentIndex = 0;
	let transitionTimer = null;
	let pollTimer = null;
	let loading = false;

	function setStatus(message) {
		status.textContent = message;
		status.hidden = !message;
	}

	function scheduleTransition() {
		window.clearTimeout(transitionTimer);
		if (!configuration || configuration.items.length === 0) {
			return;
		}

		const item = configuration.items[currentIndex];
		transitionTimer = window.setTimeout(() => {
			currentIndex = (currentIndex + 1) % configuration.items.length;
			showCurrentItem();
		}, item.duration_seconds * 1000);
	}

	function showCurrentItem() {
		if (!configuration || configuration.items.length === 0) {
			frame.removeAttribute("src");
			setStatus("No pages configured for this screen.");
			window.clearTimeout(transitionTimer);
			return;
		}

		const item = configuration.items[currentIndex];
		frame.src = item.url;
		setStatus("");
		scheduleTransition();
	}

	function schedulePoll() {
		window.clearTimeout(pollTimer);
		pollTimer = window.setTimeout(() => {
			fetchConfiguration();
		}, pollInterval);
	}

	async function fetchConfiguration() {
		if (loading) {
			return;
		}
		loading = true;

		try {
			const response = await fetch(configUrl, {
				cache: "no-store",
				credentials: "same-origin",
			});
			if (!response.ok) {
				throw new Error(`Configuration request failed: ${response.status}`);
			}

			const nextConfiguration = await response.json();
			if (
				typeof nextConfiguration.version !== "string" ||
				!Array.isArray(nextConfiguration.items)
			) {
				throw new Error("Configuration response has invalid shape");
			}

			const changed =
				configuration === null ||
				configuration.version !== nextConfiguration.version;
			configuration = nextConfiguration;
			if (changed) {
				currentIndex = 0;
				showCurrentItem();
			} else if (configuration.items.length === 0) {
				showCurrentItem();
			} else {
				setStatus("");
			}
		} catch (error) {
			console.error(error);
			if (configuration === null) {
				setStatus("Unable to load screen configuration. Retrying…");
			}
		} finally {
			loading = false;
			schedulePoll();
		}
	}

	document.addEventListener("visibilitychange", () => {
		if (!document.hidden) {
			fetchConfiguration();
		}
	});

	fetchConfiguration();
})();
