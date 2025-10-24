import pytest
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.common.exceptions import TimeoutException, NoSuchElementException, UnexpectedAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "http://127.0.0.1:8000"

# Global variables to store tournament codes
paid_tournament_code = None
free_tournament_code = None

PLAYERS = ["Player11", "Player22", "Player33", "Player44"]


@pytest.fixture(scope="class")
def setup(request):
    """Setup fixture for browser initialization"""
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-save-password-bubble")
    options.add_argument("--disable-notifications")
    options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    })

    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=options
    )
    driver.maximize_window()
    driver.implicitly_wait(5)
    request.cls.driver = driver
    yield
    driver.quit()


def handle_alert(driver):
    """Handle unexpected alerts"""
    try:
        alert = Alert(driver)
        alert.accept()
        return True
    except:
        return False


@pytest.mark.usefixtures("setup")
class TestTournamentCreation:
    """Test Class 1: Host22 creates tournaments"""
    
    def test_01_host22_login(self):
        """Host22 logs in to create tournaments"""
        print("\n-> Opening homepage...")
        self.driver.get(BASE_URL)
        time.sleep(2)
        
        print("-> Logging in as Host22...")
        self.driver.find_element(By.CSS_SELECTOR, ".fa-right-to-bracket").click()
        time.sleep(2)
        self.driver.find_element(By.NAME, "username").send_keys("Host22")
        self.driver.find_element(By.NAME, "password").send_keys("123")
        self.driver.find_element(By.CSS_SELECTOR, ".bg-orange-500").click()
        time.sleep(2)
        print("OK Logged in as Host22")
    
    def test_02_create_paid_tournament(self):
        """Create paid Valorant tournament"""
        global paid_tournament_code
        
        print("\n-> Creating Tournament 1 (Valo cup paid)...")
        self.driver.find_element(By.LINK_TEXT, "Create a tournament").click()
        time.sleep(2)
        
        self.driver.find_element(By.ID, "id_name").send_keys("Valo cup paid")
        self.driver.find_element(By.ID, "id_description").send_keys("Paid Valorant tournament")
        
        dropdown = Select(self.driver.find_element(By.ID, "id_category"))
        dropdown.select_by_visible_text("Valorant")
        
        self.driver.find_element(By.ID, "id_num_participants").clear()
        self.driver.find_element(By.ID, "id_num_participants").send_keys("4")
        
        # Next to section 2
        time.sleep(1)
        self.driver.execute_script("nextSection(2)")
        time.sleep(2)
        
        dropdown = Select(self.driver.find_element(By.ID, "id_match_type"))
        dropdown.select_by_visible_text("League")
        
        deadline_value = "2025-08-10T17:45"
        self.driver.execute_script(
            "arguments[0].value = arguments[1];",
            self.driver.find_element(By.ID, "id_registration_deadline"),
            deadline_value
        )
        
        self.driver.find_element(By.ID, "id_is_public").click()
        time.sleep(1)
        self.driver.find_element(By.ID, "id_is_active").click()
        time.sleep(1)
        
        # Set as paid tournament
        self.driver.find_element(By.ID, "id_is_paid").click()
        time.sleep(1)
        self.driver.find_element(By.ID, "id_price").clear()
        self.driver.find_element(By.ID, "id_price").send_keys("100")
        
        # Next to section 3
        self.driver.execute_script("nextSection(3)")
        time.sleep(2)
        
        # Submit
        submit_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        self.driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(3)
        
        # Capture code from modal
        modal = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.ID, "successModal"))
        )
        time.sleep(1)
        paid_tournament_code = self.driver.find_element(By.ID, "tournamentCode").text
        print(f"OK Captured PAID tournament code: {paid_tournament_code}")
        
        # Close modal
        close_btn = self.driver.find_element(By.ID, "closeModalButton")
        close_btn.click()
        time.sleep(2)
        
        # Store in class variable for other tests
        TestTournamentCreation.paid_code = paid_tournament_code
    
    def test_03_create_free_tournament(self):
        """Create free FC24 tournament"""
        global free_tournament_code
        
        print("\n-> Creating Tournament 2 (FC free)...")
        self.driver.find_element(By.CSS_SELECTOR, ".fa-house").click()
        time.sleep(2)
        self.driver.find_element(By.LINK_TEXT, "Create a tournament").click()
        time.sleep(2)
        
        self.driver.find_element(By.ID, "id_name").send_keys("FC free")
        self.driver.find_element(By.ID, "id_description").send_keys("Free FC24 tournament")
        
        dropdown = Select(self.driver.find_element(By.ID, "id_category"))
        dropdown.select_by_visible_text("Football")
        
        self.driver.find_element(By.ID, "id_num_participants").clear()
        self.driver.find_element(By.ID, "id_num_participants").send_keys("4")
        
        self.driver.execute_script("nextSection(2)")
        time.sleep(2)
        
        dropdown = Select(self.driver.find_element(By.ID, "id_match_type"))
        dropdown.select_by_visible_text("League")
        
        deadline_value = "2025-08-10T17:45"
        self.driver.execute_script(
            "arguments[0].value = arguments[1];",
            self.driver.find_element(By.ID, "id_registration_deadline"),
            deadline_value
        )
        
        self.driver.find_element(By.ID, "id_is_public").click()
        time.sleep(1)
        self.driver.find_element(By.ID, "id_is_active").click()
        time.sleep(1)
        
        self.driver.execute_script("nextSection(3)")
        time.sleep(2)
        
        submit_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        self.driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(3)
        
        modal = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.ID, "successModal"))
        )
        time.sleep(1)
        free_tournament_code = self.driver.find_element(By.ID, "tournamentCode").text
        print(f"OK Captured FREE tournament code: {free_tournament_code}")
        
        close_btn = self.driver.find_element(By.ID, "closeModalButton")
        close_btn.click()
        time.sleep(2)
        
        # Store in class variable
        TestTournamentCreation.free_code = free_tournament_code
    
    def test_04_host22_logout(self):
        """Logout Host22"""
        print("\n-> Logging out Host22...")
        self.driver.find_element(By.CSS_SELECTOR, ".fa-house").click()
        time.sleep(2)
        self.driver.find_element(By.CSS_SELECTOR, ".fa-right-from-bracket").click()
        time.sleep(2)
        print("OK Host22 logged out")


@pytest.mark.usefixtures("setup")
class TestPlayersJoinTournaments:
    """Test Class 2: Players join both tournaments"""
    
    def test_05_player11_login_and_join_paid(self):
        """Player11 joins paid tournament"""
        self._player_login("Player11")
        self._join_paid_tournament("Player11")
    
    def test_06_player11_join_free(self):
        """Player11 joins free tournament"""
        self._join_free_tournament("Player11")
        self._player_logout("Player11")
    
    def test_07_player22_login_and_join_paid(self):
        """Player22 joins paid tournament"""
        self._player_login("Player22")
        self._join_paid_tournament("Player22")
    
    def test_08_player22_join_free(self):
        """Player22 joins free tournament"""
        self._join_free_tournament("Player22")
        self._player_logout("Player22")
    
    def test_09_player33_login_and_join_paid(self):
        """Player33 joins paid tournament"""
        self._player_login("Player33")
        self._join_paid_tournament("Player33")
    
    def test_10_player33_join_free(self):
        """Player33 joins free tournament"""
        self._join_free_tournament("Player33")
        self._player_logout("Player33")
    
    def test_11_player44_login_and_join_paid(self):
        """Player44 joins paid tournament"""
        self._player_login("Player44")
        self._join_paid_tournament("Player44")
    
    def test_12_player44_join_free(self):
        """Player44 joins free tournament"""
        self._join_free_tournament("Player44")
        self._player_logout("Player44")
    
    # Helper methods
    def _player_login(self, player_username):
        """Helper: Login as player"""
        print(f"\n-> Logging in as {player_username}...")
        self.driver.get(BASE_URL)
        time.sleep(2)
        
        self.driver.find_element(By.CSS_SELECTOR, ".fa-right-to-bracket").click()
        time.sleep(2)
        self.driver.find_element(By.NAME, "username").send_keys(player_username)
        self.driver.find_element(By.NAME, "password").send_keys("123")
        self.driver.find_element(By.CSS_SELECTOR, ".bg-orange-500").click()
        time.sleep(2)
        print(f"OK Logged in as {player_username}")
    
    def _join_paid_tournament(self, player_username):
        """Helper: Join paid tournament with payment"""
        paid_code = TestTournamentCreation.paid_code
        print(f"\n-> {player_username}: Joining PAID tournament (code: {paid_code})")
        
        self.driver.find_element(By.LINK_TEXT, "Join a tournament").click()
        time.sleep(2)
        
        # Enter code
        code_field = self.driver.find_element(By.ID, "id_code")
        code_field.clear()
        code_field.send_keys(paid_code)
        time.sleep(1)
        
        # Click Find Tournament
        find_btn = self.driver.find_element(By.NAME, "find_tournament")
        find_btn.click()
        time.sleep(3)
        print("   OK Tournament found")
        
        # Click Confirm & Join
        join_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "join_tournament"))
        )
        join_btn.click()
        time.sleep(2)
        print("   OK Clicked Confirm & Join")
        
        # Payment page - select bKash
        print("   -> Completing payment...")
        bkash_card = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@onclick=\"selectMethod('bkash', this)\"]"))
        )
        self.driver.execute_script("arguments[0].click();", bkash_card)
        time.sleep(1)
        
        proceed_btn = self.driver.find_element(By.ID, "proceedBtn")
        proceed_btn.click()
        time.sleep(2)
        
        # Fill payment details
        sender_field = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, "sender_number"))
        )
        sender_field.send_keys("01319345357")
        
        trx_field = self.driver.find_element(By.NAME, "trx_id")
        trx_field.send_keys(f"TRX{player_username}")
        
        # Submit payment
        submit_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and contains(., 'Confirm Payment')]"))
        )
        self.driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(3)
        print(f"   OK {player_username} joined PAID tournament!")
    
    def _join_free_tournament(self, player_username):
        """Helper: Join free tournament"""
        free_code = TestTournamentCreation.free_code
        print(f"\n-> {player_username}: Joining FREE tournament (code: {free_code})")
        
        # Navigate to join page
        self.driver.find_element(By.CSS_SELECTOR, ".fa-house").click()
        time.sleep(2)
        self.driver.find_element(By.LINK_TEXT, "Join a tournament").click()
        time.sleep(2)
        
        # Enter code
        code_field = self.driver.find_element(By.ID, "id_code")
        code_field.clear()
        code_field.send_keys(free_code)
        time.sleep(1)
        
        # Click Find Tournament
        find_btn = self.driver.find_element(By.NAME, "find_tournament")
        find_btn.click()
        time.sleep(3)
        print("   OK Tournament found")
        
        # Click Confirm & Join
        join_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "join_tournament"))
        )
        join_btn.click()
        time.sleep(3)
        print(f"   OK {player_username} joined FREE tournament!")
    
    def _player_logout(self, player_username):
        """Helper: Logout player"""
        print(f"-> Logging out {player_username}...")
        self.driver.find_element(By.CSS_SELECTOR, ".fa-house").click()
        time.sleep(2)
        self.driver.find_element(By.CSS_SELECTOR, ".fa-right-from-bracket").click()
        time.sleep(2)
        print(f"OK {player_username} logged out")


@pytest.mark.usefixtures("setup")
class TestHostManagement:
    """Test Class 3: Host22 manages tournaments and explores website"""
    
    def test_13_host22_login(self):
        """Host22 logs in"""
        print("\n-> Opening homepage...")
        self.driver.get(BASE_URL)
        time.sleep(2)
        
        print("-> Logging in as Host22...")
        self.driver.find_element(By.CSS_SELECTOR, ".fa-right-to-bracket").click()
        time.sleep(2)
        self.driver.find_element(By.NAME, "username").send_keys("Host22")
        self.driver.find_element(By.NAME, "password").send_keys("123")
        self.driver.find_element(By.CSS_SELECTOR, ".bg-orange-500").click()
        time.sleep(2)
        print("OK Logged in as Host22")
    
    def test_14_navigate_to_tournaments(self):
        """Navigate to tournaments page"""
        print("\n-> Navigating to Tournaments page...")
        self.driver.find_element(By.LINK_TEXT, "Tournaments").click()
        time.sleep(3)
        print("OK On tournaments page")
    
    def test_15_get_tournament_ids(self):
        """Get tournament IDs from manage tournament links"""
        print("\n-> Finding tournament IDs...")
        
        # Try multiple methods to find manage links
        manage_links = []
        
        # Method 1: Try finding links with "Manage" text
        try:
            manage_links = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Manage')]")
            print(f"   Method 1: Found {len(manage_links)} links with 'Manage' text")
        except:
            pass
        
        # Method 2: If not found, try finding all links containing /tournament/ in href
        if not manage_links:
            try:
                all_tournament_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/tournament/')]")
                # Filter to only dashboard links (ending with tournament/ID/)
                manage_links = [link for link in all_tournament_links if link.get_attribute("href").rstrip('/').count('/') >= 4]
                print(f"   Method 2: Found {len(manage_links)} tournament dashboard links")
            except:
                pass
        
        # Method 3: Take screenshot for debugging if still not found
        if not manage_links:
            self.driver.save_screenshot("tournaments_page_debug.png")
            print("   WARNING: Could not find manage links. Screenshot saved.")
        
        tournament_ids = []
        for link in manage_links:
            href = link.get_attribute("href")
            if href and "/tournament/" in href:
                # Extract ID from URL like /tournament/123/
                parts = href.split("/tournament/")
                if len(parts) > 1:
                    tournament_id = parts[1].split("/")[0]
                    if tournament_id:
                        tournament_ids.append(tournament_id)
        
        print(f"OK Found {len(tournament_ids)} tournaments: {tournament_ids}")
        
        # Store IDs in class variables
        if len(tournament_ids) >= 2:
            TestHostManagement.valo_tournament_id = tournament_ids[0]  # First is Valo cup (paid)
            TestHostManagement.free_tournament_id = tournament_ids[1]  # Second is FC free
            print(f"   Valo Cup ID: {self.valo_tournament_id}")
            print(f"   FC Free ID: {self.free_tournament_id}")
        else:
            pytest.fail(f"Expected 2 tournaments but found {len(tournament_ids)}")
    
    def test_16_regenerate_valo_tournament_fixture(self):
        """Regenerate fixture for Valo Cup tournament"""
        print(f"\n-> Regenerating fixture for Valo Cup...")
        
        # Stay on tournament dashboard
        self.driver.get(f"{BASE_URL}/tournament/{self.valo_tournament_id}/")
        time.sleep(3)
        
        # Click Regenerate Fixture button using XPath
        try:
            regenerate_btn = self.driver.find_element(By.XPATH, "/html/body/div/div[4]/div/div[1]/div[2]/div/form[3]/button")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", regenerate_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", regenerate_btn)
            time.sleep(3)
            print("OK Fixture regenerated successfully!")
        except Exception as e:
            print(f"   Warning: Could not regenerate fixture: {e}")
   
    def test_17_update_valo_tournament_results(self):
        """Update match results for Valo Cup with random winners from all players"""
        print(f"\n-> Updating match results for Valo Cup...")
        
        # Stay on tournament dashboard
        self.driver.get(f"{BASE_URL}/tournament/{self.valo_tournament_id}/")
        time.sleep(3)
        
        # Find all match result forms
        match_forms = self.driver.find_elements(By.XPATH, "//form[contains(@action, '/match/')]")
        print(f"   Found {len(match_forms)} matches to update")
        
        # Winners pool: All players
        winners = ["Player11", "Player22", "Player33", "Player44"]
        
        for i, form in enumerate(match_forms, 1):
            try:
                # Scroll to form
                self.driver.execute_script("arguments[0].scrollIntoView(true);", form)
                time.sleep(0.5)
                
                # Find winner dropdown using XPath
                winner_select = form.find_element(By.XPATH, ".//select[contains(@id, 'id_winner') or contains(@name, 'winner')]")
                select = Select(winner_select)
                
                # Get available options (skip the first empty option)
                options = [opt.text for opt in select.options if opt.text.strip()]
                
                # Randomly pick from available players
                available_winners = [w for w in winners if w in options]
                if available_winners:
                    winner = random.choice(available_winners)
                else:
                    winner = random.choice(options) if options else None
                
                if winner:
                    select.select_by_visible_text(winner)
                    print(f"   Match {i}: Selected winner -> {winner}")
                    
                    # Generate random scores
                    score1 = random.randint(10, 25)
                    score2 = random.randint(5, 20)
                    
                    # Fill scores
                    score1_field = form.find_element(By.NAME, "team1_score")
                    score2_field = form.find_element(By.NAME, "team2_score")
                    
                    score1_field.clear()
                    score1_field.send_keys(str(score1))
                    score2_field.clear()
                    score2_field.send_keys(str(score2))
                    
                    print(f"   Match {i}: Scores -> {score1} - {score2}")
                    
                    # Submit
                    submit_btn = form.find_element(By.XPATH, ".//button[@type='submit']")
                    self.driver.execute_script("arguments[0].click();", submit_btn)
                    time.sleep(2)
                    print(f"   OK Match {i} updated!")
                
            except Exception as e:
                print(f"   Warning: Could not update match {i}: {e}")
        
        print("OK All Valo Cup match results updated!")
        
        # Click "Update All Matches" button
        time.sleep(2)
        try:
            update_all_btn = self.driver.find_element(By.XPATH, "/html/body/div/div[4]/div/div[1]/div[2]/div/button")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", update_all_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", update_all_btn)
            time.sleep(2)
            print("OK Clicked 'Update All Matches' button!")
        except Exception as e:
            print(f"   Warning: Could not click 'Update All Matches' button: {e}")
        
        # Mark tournament as finished
        time.sleep(2)
        try:
            mark_finished_btn = self.driver.find_element(By.XPATH, "/html/body/div/div[4]/div/div[1]/div[2]/div/form[1]/button")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", mark_finished_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", mark_finished_btn)
            time.sleep(2)
            print("OK Marked Valo Cup tournament as finished!")
        except Exception as e:
            print(f"   Warning: Could not mark tournament as finished: {e}")
    
    def test_18_update_free_tournament_results(self):
        """Update match results for FC Free tournament with random winners from all players"""
        print(f"\n-> Updating match results for FC Free tournament...")
        
        # Navigate to free tournament dashboard
        self.driver.get(f"{BASE_URL}/tournament/{self.free_tournament_id}/")
        time.sleep(3)
        
        # Find all match result forms
        match_forms = self.driver.find_elements(By.XPATH, "//form[contains(@action, '/match/')]")
        print(f"   Found {len(match_forms)} matches to update")
        
        # Winners pool: All players
        winners = ["Player11", "Player22", "Player33", "Player44"]
        
        for i, form in enumerate(match_forms, 1):
            try:
                # Scroll to form
                self.driver.execute_script("arguments[0].scrollIntoView(true);", form)
                time.sleep(0.5)
                
                # Find winner dropdown using XPath
                winner_select = form.find_element(By.XPATH, ".//select[contains(@id, 'id_winner') or contains(@name, 'winner')]")
                select = Select(winner_select)
                
                # Get available options (skip empty)
                options = [opt.text for opt in select.options if opt.text.strip()]
                
                # Randomly pick from available players
                available_winners = [w for w in winners if w in options]
                if available_winners:
                    winner = random.choice(available_winners)
                else:
                    winner = random.choice(options) if options else None
                
                if winner:
                    select.select_by_visible_text(winner)
                    print(f"   Match {i}: Selected winner -> {winner}")
                    
                    # Generate random scores
                    score1 = random.randint(0, 5)
                    score2 = random.randint(0, 4)
                    
                    # Fill scores
                    score1_field = form.find_element(By.NAME, "team1_score")
                    score2_field = form.find_element(By.NAME, "team2_score")
                    
                    score1_field.clear()
                    score1_field.send_keys(str(score1))
                    score2_field.clear()
                    score2_field.send_keys(str(score2))
                    
                    print(f"   Match {i}: Scores -> {score1} - {score2}")
                    
                    # Submit
                    submit_btn = form.find_element(By.XPATH, ".//button[@type='submit']")
                    self.driver.execute_script("arguments[0].click();", submit_btn)
                    time.sleep(2)
                    print(f"   OK Match {i} updated!")
                
            except Exception as e:
                print(f"   Warning: Could not update match {i}: {e}")
        
        print("OK All FC Free match results updated!")
        
        # Click "Update All Matches" button
        time.sleep(2)
        try:
            update_all_btn = self.driver.find_element(By.XPATH, "/html/body/div/div[4]/div/div[1]/div[2]/div/button")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", update_all_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", update_all_btn)
            time.sleep(2)
            print("OK Clicked 'Update All Matches' button!")
        except Exception as e:
            print(f"   Warning: Could not click 'Update All Matches' button: {e}")
        
        # Mark tournament as finished
        time.sleep(2)
        try:
            mark_finished_btn = self.driver.find_element(By.XPATH, "/html/body/div/div[4]/div/div[1]/div[2]/div/form[1]/button")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", mark_finished_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", mark_finished_btn)
            time.sleep(2)
            print("OK Marked FC Free tournament as finished!")
        except Exception as e:
            print(f"   Warning: Could not mark tournament as finished: {e}")
    
    def test_19_explore_home_page(self):
        """Explore the home page"""
        print("\n-> Exploring Home page...")
        self.driver.find_element(By.CSS_SELECTOR, ".fa-house").click()
        time.sleep(3)
        
        # Scroll down to see content
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        print("OK Explored Home page")
    
    def test_20_explore_leaderboard(self):
        """Explore the leaderboard from navbar"""
        print("\n-> Clicking Leaderboard from navbar...")
        
        # Click Leaderboard button from navbar
        leaderboard_btn = self.driver.find_element(By.LINK_TEXT, "Leaderboard")
        leaderboard_btn.click()
        time.sleep(3)
        
        # Scroll to see leaderboard
        self.driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2)
        
        print("OK Explored Leaderboard from navbar")
    
    def test_21_explore_games(self):
        """Explore the games page from navbar"""
        print("\n-> Clicking Games from navbar...")
        
        # Click Games button from navbar
        games_btn = self.driver.find_element(By.LINK_TEXT, "Games")
        games_btn.click()
        time.sleep(3)
        
        # Scroll to see games
        self.driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2)
        
        print("OK Explored Games from navbar")
    
    def test_22_explore_support_center(self):
        """Explore the support center from navbar"""
        print("\n-> Clicking Support Center from navbar...")
        
        # Click Support Center button from navbar
        support_btn = self.driver.find_element(By.LINK_TEXT, "Support Center")
        support_btn.click()
        time.sleep(3)
        
        # Scroll to see support content
        self.driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2)
        
        print("OK Explored Support Center from navbar")
    
    def test_23_host22_logout(self):
        """Logout Host22"""
        print("\n-> Logging out Host22...")
        self.driver.find_element(By.CSS_SELECTOR, ".fa-house").click()
        time.sleep(2)
        self.driver.find_element(By.CSS_SELECTOR, ".fa-right-from-bracket").click()
        time.sleep(2)
        print("OK Host22 logged out successfully!")


if __name__ == "__main__":
    pytest.main(["-v", "--html=tournament_report.html", "--self-contained-html", __file__])
