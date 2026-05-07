Feature: Sample feature

  @regression @PROJ-124 @PROJ-125
  Scenario Outline: Validate user input
    Given I enter <field> as <value>
    When I validate the input
    Then the result should be <result>

    Examples:
      | field    | value      | result |
      | email    | valid@test | pass   |
      | email    | invalid    | fail   |
      | username | admin      | pass   |
