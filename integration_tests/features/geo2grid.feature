Feature: Test geo2grid output images
  This takes test data from source and runs it through the command provided.
  It then compares the new image with the expected output.

  Scenario Outline: Test geo2grid images
    Given input data from <source>
    When <command> runs
    Then the output matches with the files in <output>

  Examples: ABI
    | command                                                  | source          | output           |
    | geo2grid.sh -r abi_l1b -w geotiff --num-workers 8 -vv -f | abi/input/test1 | abi/output/test1 |
    | geo2grid.sh -r abi_l1b -w geotiff --num-workers 8 -vv -f | abi/input/test2 | abi/output/test2 |
    | geo2grid.sh -r abi_l1b -w geotiff --num-workers 8 -vv -f | abi/input/test3 | abi/output/test3 |
    | geo2grid.sh -r abi_l1b -w geotiff --num-workers 8 -vv -f | abi/input/test4 | abi/output/test4 |
