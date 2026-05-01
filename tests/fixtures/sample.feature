Feature: User Management API
  As a system administrator
  I want to manage user accounts
  So that I can control access to the system

  Background:
    Given the API is running
    And I have admin credentials

  @smoke @PROJ-123
  Scenario: Create a new user
    Given I have user data
    When I send POST request to url 'https://api.example.com/users'
    Then the response status should be 201
    And the user should be created in the database

  @regression @PROJ-124 @PROJ-125
  Scenario Outline: Validate user input
    Given I have user data with <field> as <value>
    When I call read('workflows/validation.feature')
    Then the validation should <result>
    
    Examples:
      | field    | value       | result |
      | email    | valid@test  | pass   |
      | email    | invalid     | fail   |
      | username | admin       | pass   |

  @integration @PROJ-126
  Scenario: Login with page object
    Given I navigate to the login page
    When I call read('pages/loginPage.feature')
    And I enter credentials
    Then I should be logged in
    And SELECT * FROM sessions WHERE user_id = 1

  Scenario: API endpoint with baseUrl
    Given baseUrl + '/api/v1/users'
    When method GET
    Then status 200
